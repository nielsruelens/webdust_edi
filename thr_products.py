from openerp.osv import osv
from openerp.tools.translate import _
import logging
from openerp.addons.product.product import check_ean
import threading
from openerp import pooler

class product(osv.Model):

    _name = "product.product"
    _inherit = 'product.product'
    _description = "Product extensions"

    log = logging.getLogger(None)

    properties = []
    categories = []

    header = []
    invalid = []

    thr = False


    def clear_globals(self, cr, uid):
        ''' product.product:clear_globals()
        -----------------------------------
        This method clears all the global attributes
        required for the THR upload.
        -------------------------------------------- '''
        self.properties = []
        self.categories = []
        self.header = []
        self.invalid = []
        self.thr = False

    def get_all_properties(self, cr, uid):
        ''' product.product:get_all_properties()
        ----------------------------------------
        This method reads all the properties currently
        defined in the system for fast use during the THR
        master upload process.
        ------------------------------------------------- '''

        self.log.info('UPLOAD_THR-PRODUCTS: reading all the property masterdata.')
        prop_db = self.pool.get('webdust.property')
        self.properties = prop_db.browse(cr, uid, prop_db.search(cr, uid, []), context=None)

        # Convert the OpenERP browse record to a simple list to avoid cursor problems
        self.properties = [{'id':x.id, 'name':x.name} for x in self.properties]
        return True

    def get_all_categories(self, cr, uid):
        ''' product.product:get_all_categories()
        ----------------------------------------
        This method reads all the categories currently
        defined in the system for fast use during the THR
        master upload process.
        ------------------------------------------------- '''

        self.log.info('UPLOAD_THR-PRODUCTS: reading all the category masterdata.')
        cat_db = self.pool.get('product.category')
        self.categories = cat_db.browse(cr, uid, cat_db.search(cr, uid, []), context=None)

        # Convert the OpenERP browse record to a simple list to avoid cursor problems
        self.categories = [{'id':x.id, 'code':x.code} for x in self.categories]
        return True



    def upload_thr_master_detail(self, cr, uid, content, no_of_processes=2,do_supplier_removal=True, context=None):
        ''' product.product:upload_thr_master_detail()
        ----------------------------------------------
        This method is the heart of the THR master data import.
        It will loop over all documents, store all global
        variables and create/update all the products. It will
        also make sure to split processing in multiple threads.
        ------------------------------------------------------- '''

        self.log.info('UPLOAD_THR-PRODUCTS: starting on the products.')
        self.header = content[0]
        del content[0]

        # Search THR as a partner
        # -----------------------
        self.log.info('UPLOAD_THR-PRODUCTS: searching for THR as a partner.')
        (self.thr,) = self.pool.get('res.partner').search(cr, uid, [('name', '=', 'THR')],context=context)
        if not self.thr:
            self.log.error('UPLOAD_THR-PRODUCTS: could not find partner THR, aborting process.')
            return True


        # Get all the property & category definitions
        # -------------------------------------------
        self.get_all_properties(cr, uid)
        self.get_all_categories(cr, uid)



        # Fix all EAN codes, might be a couple missing leading zeroes
        # Reason this is done beforehand is because we want to be
        # able to search for all existing products in 1 go, see below.
        # ------------------------------------------------------------
        self.log.info('UPLOAD_THR-PRODUCTS: checking if all the EAN codes are 13 chars long.')
        for i, line in enumerate(content):
            if len(line[1]) < 13:
                self.log.warning('UPLOAD_THR-PRODUCTS: adding missing leading zeroes to EAN {!s}'.format(line[1]))
                line[1] = '0' * (13-len(line[1])) + line[1]
                content[i+1] = line


        # Remove THR as the supplier for any products that aren't mentioned
        # in the file. The reason this step is optional is due to the fact
        # that we're also processing this method using the EDI flow, in which case
        # the file will be practically empty and we don't want to accidentally delete all data!
        # -------------------------------------------------------------------------------------
        if do_supplier_removal:
            self.remove_obsolete_products(cr, uid, content, context=context)



        # Split the actual processing of the content into
        # several threads to hopefully speed up performance
        # -------------------------------------------------
        threads = []
        for i in xrange(no_of_processes):
            start = len(content) / no_of_processes * i
            end = len(content) / no_of_processes * (i+1)
            if i+1 == no_of_processes: end = len(content)
            t = threading.Thread(target=self._content_thread, args=(cr, uid, content[start:end], context))
            threads.append(t)
            t.start()

        self.log.info('UPLOAD_THR-PRODUCTS: Waiting till all threads have finished.')
        for t in threads:
            t.join()
        self.log.info('UPLOAD_THR-PRODUCTS: All threads have finished.')





    def _content_thread(self, cr, uid, content, context=None):
        ''' product.product:_content_thread()
        -------------------------------------
        This method is called by upload_thr_master_detail()
        several times in a multi threaded context to speed up
        processing for several tens of thousand products.
        Based on the records it receives, it will attempt to
        create or update a given product. If a product it is
        given is invalid, it will store it in self.invalid
        so the upload can be given another shot using the EDI
        flow.
        ------------------------------------------------------ '''


        # Create a new cursor for this thread
        # -----------------------------------
        new_cr = pooler.get_db(cr.dbname).cursor()

        try:

            # Get all the ids + content for all the products that already exist.
            # ------------------------------------------------------------------
            self.log.info('UPLOAD_THR-PRODUCTS: reading pre-existing products.')
            prod_ids = self.search(new_cr, uid, [('ean13', 'in', [ x[1] for x in content ])])
            all_existing = self.browse(new_cr, uid, prod_ids, context=context)


            # Process all the products
            # ------------------------
            for i, line in enumerate(content):
                i = i + 1

                if i == 10:
                    new_cr.commit()
                    return True

                self.log.info('UPLOAD_THR-PRODUCTS: processing product with EAN {!s} ({!s} of {!s})'.format(line[1], i, len(content)))
                existing = next((x for x in all_existing if x.ean13 == line[1]), None)

                # Commit every 200 products to make sure
                # lost work in case of problems is limited
                # ----------------------------------------
                if i % 200 == 0:
                    new_cr.commit()


                # Creation of a new product
                # -------------------------
                if not existing:

                    prod = self.create_new_product(new_cr, uid,line)
                    if 'rejection' in prod:
                        self.invalid.append(line)
                        self.log.warning('UPLOAD_THR-PRODUCTS: {!s}'.format(prod['rejection']))

                # Updating an existing product
                # ----------------------------
                else:
                    self.update_product(new_cr, uid,line, existing)

            new_cr.commit()
        finally:
            new_cr.close()
        return True




    def create_new_product(self, cr, uid, line):
        ''' product.product:create_new_product()
        ----------------------------------------
        This method creates a new product in the THR master
        data upload process.
        --------------------------------------------------- '''


        vals = {}

        # Check if the EAN is valid
        # -------------------------
        if line[1] and check_ean(line[1]):
            vals['ean13'] = line[1]
        else:
            return {'rejection': 'product rejected because EAN is invalid.'}


        # Determine the category
        # ----------------------
        if line[10]:
            vals['categ_id'] = line[10]
        elif line[8]:
            vals['categ_id'] = line[8]
        elif line[6]:
            vals['categ_id'] = line[6]
        elif line[4]:
            vals['categ_id'] = line[4]
        elif line[2]:
            vals['categ_id'] = line[2]
        else:
            return {'rejection': 'Product rejected because category is not provided.'}


        vals['categ_id'] = next((x['id'] for x in self.categories if x['code'] == vals['categ_id']),None)
        if not vals['categ_id']:
            return {'rejection': 'Product rejected because category is unknown.'}


        vals['name'] = ' '.join((line[41], line[40], line[42]))
        if not vals['name']:
            return {'rejection': 'Product rejected because name could not be determined.'}

        # THR product code
        # ----------------
        supplier = {}
        supplier['name'] = self.thr
        supplier['min_qty'] = 1
        supplier['product_code'] = line[0]
        vals['seller_ids'] =  [(0, False, supplier)]

        # Properties
        vals['properties'] = []
        for i, prop in enumerate(line):
            if i < 24 or not prop:
                continue
            new_prop = {}
            new_prop['name'] = next((x['id'] for x in self.properties if x['name'] == self.header[i]),None)
            if not new_prop['name']:
                continue
            new_prop['value'] = prop
            vals['properties'].append([0,False,new_prop])


        vals['short_description'] = line[12]
        vals['description_sale'] = line[13]
        vals['procure_method'] = 'make_to_order'
        vals['type'] = 'product'
        vals['state'] = 'draft'
        vals['recommended_price'] = line[24]
        return {'id' : self.create(cr, uid, vals, context=None)}






    def update_product(self, cr, uid, line, product):
        ''' product.product:update_product()
        ------------------------------------
        This method updates a given product in the THR master
        data upload process.
        ----------------------------------------------------- '''

        vals = {}
        supplier_db = self.pool.get('product.supplierinfo')
        prop_db = self.pool.get('webdust.product.property')


        vals['name'] = ' '.join((line[41], line[40], line[42]))
        if not vals['name']:
            del vals['name']

        # Determine the category
        # ----------------------
        if line[10]:
            vals['categ_id'] = line[10]
        elif line[8]:
            vals['categ_id'] = line[8]
        elif line[6]:
            vals['categ_id'] = line[6]
        elif line[4]:
            vals['categ_id'] = line[4]
        elif line[2]:
            vals['categ_id'] = line[2]

        if 'categ_id' in vals:
            vals['categ_id'] = next((x['id'] for x in self.categories if x['code'] == vals['categ_id']),None)
        if vals['categ_id'] == product.categ_id.id:
            del vals['categ_id']

        # THR product code
        # ----------------
        seller = next((x for x in product.seller_ids if x.name.id == self.thr),None)
        if not seller:
            supplier = {}
            supplier['name'] = self.thr
            supplier['min_qty'] = 1
            supplier['product_code'] = line[0]
            vals['seller_ids'] =  [(0, False, supplier)]
        else:
            if seller.product_code != line[0]:
                supplier_db.write(cr, uid, seller.id, {'product_code' : line[0]}, context=None)

        # Properties
        vals['properties'] = []
        for i, prop in enumerate(line):
            if i < 24 or not prop:
                continue
            prop_id = next((x['id'] for x in self.properties if x['name'] == self.header[i]),None)
            if not prop_id:
                continue
            property = next((x for x in product.properties if x.name.id == prop_id),None)
            if not property:
                new_prop = {}
                new_prop['value'] = prop
                new_prop['name'] = prop_id
                vals['properties'].append([0,False,new_prop])
            else:
                if property.value != prop:
                    prop_db.write(cr, uid, property.id, {'value' : prop}, context=None)
        if not vals['properties']:
            del vals['properties']


        vals['short_description'] = line[12]
        vals['description_sale'] = line[13]
        vals['recommended_price'] = line[24]
        return {'id' : self.write(cr, uid, [product.id], vals, context=None)}



    def remove_obsolete_products(self, cr, uid, content, context=None):
        ''' product.product:remove_obsolete_products()
        ----------------------------------------------
        This method calculates which products are currently
        listed as being supplied by THR and checks if they're
        still mentioned in the to-be imported content. If not,
        it means THR no longer supplies this product and the
        listing is removed as such.
        ------------------------------------------------------ '''

        self.log.info('UPLOAD_THR-PRODUCTS: Removing supplier information for products THR no longer supplies.')

        supplier_db = self.pool.get('product.supplierinfo')

        # All products mentioned in the file
        # ----------------------------------
        current = set([x[0] for x in content])

        # All products currently supplied by THR
        # --------------------------------------
        old = supplier_db.search(cr, uid, [('name', '=', self.thr)],context=context)
        old_total = supplier_db.browse(cr, uid, old, context=context)
        old = set([x.product_code for x in old_total])

        # These products are no longer supplied
        # -------------------------------------
        obsolete = old - current
        obsolete = [x for x in old_total if x.product_code in obsolete]

        # Remove the supplier info
        # ------------------------
        for info in obsolete:
            vals = {'seller_ids' : [(2, info.id,False)]}
            self.write(cr, uid, [info.product_id.id], vals, context=context)

        cr.commit()
















