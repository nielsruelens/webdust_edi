from openerp.osv import osv
from openerp.tools.translate import _
import logging
from openerp.addons.product.product import check_ean
import threading
from openerp import pooler

class product(osv.Model):

    _name = "product.product"
    _inherit = 'product.product'
    _description = "Product location extensions"

    log = logging.getLogger(None)

    properties = []
    categories = []

    header = []
    indexes = {}
    invalid = []
    warnings = []


    def clear_globals(self, cr, uid):
        ''' product.product:clear_globals()
        -----------------------------------
        This method clears all the global attributes
        required for the THR upload.
        -------------------------------------------- '''
        self.properties = []
        self.categories = []
        self.header = []
        self.indexes = {}
        self.invalid = []
        self.warnings = []

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


    def get_file_column_indexes(self, cr, uid):

        self.indexes['product_code'] = self.header.index('ProductID')
        self.indexes['ean13'] = self.header.index('EANcode')
        self.indexes['name'] = self.header.index('Korte Omschrijving')
        self.indexes['long_description'] = self.header.index('Lange Omschrijving')
        self.indexes['first_category'] = self.header.index('Classificatie Niveau 1')
        self.indexes['first_image'] = self.header.index('Bestand Afbeelding 1')
        self.indexes['recommended_price'] = self.header.index('Consumentenadviesprijs (incl)')
        return True


    def upload_thr_master_detail(self, cr, uid, content, context=None):
        ''' product.product:upload_thr_master_detail()
        ----------------------------------------------
        This method is the heart of the THR master data import.
        It will loop over all documents, store all global
        variables and create/update all the products. It will
        also make sure to split processing in multiple threads.
        ------------------------------------------------------- '''

        helpdesk_db = self.pool.get('crm.helpdesk')
        header = 'An error occurred during the THR masterdata import.'


        self.log.info('UPLOAD_THR-PRODUCTS: starting on the products.')
        self.header = content[0]
        del content[0]

        # Search THR as a partner
        # -----------------------
        self.log.info('UPLOAD_THR-PRODUCTS: searching for THR as a partner.')
        self.read_thr_partner(cr, uid)
        if not self.thr:
            self.log.error('UPLOAD_THR-PRODUCTS: could not find partner THR, aborting process.')
            helpdesk_db.create_simple_case(cr, uid, header, 'UPLOAD_THR-PRODUCTS: could not find partner THR, aborting process.')
            return True


        # Get all the property & category definitions
        # -------------------------------------------
        self.get_file_column_indexes(cr, uid)
        self.get_all_properties(cr, uid)
        self.get_all_categories(cr, uid)


        # Fix all EAN codes, might be a couple missing leading zeroes
        # Reason this is done beforehand is because we want to be
        # able to search for all existing products in 1 go, see below.
        # ------------------------------------------------------------
        self.log.info('UPLOAD_THR-PRODUCTS: checking if all the EAN codes are 13 chars long.')
        for i, line in enumerate(content):
            if len(line[self.indexes['ean13']]) < 13:
                warning = 'UPLOAD_THR-PRODUCTS: adding missing leading zeroes to EAN {!s}'.format(line[self.indexes['ean13']])
                self.log.warning(warning)
                self.warnings.append(warning)
                line[self.indexes['ean13']] = '0' * (13-len(line[self.indexes['ean13']])) + line[self.indexes['ean13']]
                #content[i+1] = line



        # Split the actual processing of the content into
        # several threads to hopefully speed up performance
        # -------------------------------------------------
        threads = []
        for i in xrange(self.settings.no_of_processes):
            start = len(content) / self.settings.no_of_processes * i
            end = len(content) / self.settings.no_of_processes * (i+1)
            if i+1 == self.settings.no_of_processes: end = len(content)
            t = threading.Thread(target=self._content_thread_master, args=(cr, uid, content[start:end], context))
            threads.append(t)
            t.start()

        self.log.info('UPLOAD_THR-PRODUCTS: Waiting till all threads have finished.')
        for t in threads:
            t.join()
        self.log.info('UPLOAD_THR-PRODUCTS: All threads have finished.')


        # Write any warnings to a CRM helpdesk case
        # -----------------------------------------
        if self.warnings:
            warning = '\n'.join(self.warnings)
            helpdesk_db.create_simple_case(cr, uid, 'These warnings generated during the THR masterdata upload need to be validated.', warning)
            return True



    def _content_thread_master(self, cr, uid, content, context=None):
        ''' product.product:_content_thread_master()
        --------------------------------------------
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
            prod_ids = self.search(new_cr, uid, [('ean13', 'in', [ x[self.indexes['ean13']] for x in content ])])
            all_existing = self.read(new_cr, uid, prod_ids, ['id', 'ean13', 'categ_id', 'seller_ids', 'properties'], context=context)


            # Process all the products
            # ------------------------
            for i, line in enumerate(content):
                i = i + 1

                self.log.info('UPLOAD_THR-PRODUCTS: processing product with EAN {!s} ({!s} of {!s})'.format(line[self.indexes['ean13']], i, len(content)))
                existing = next((x for x in all_existing if x['ean13'] == line[self.indexes['ean13']]), None)

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
                        warning ='UPLOAD_THR-PRODUCTS: {!s}'.format(prod['rejection'])
                        self.log.warning(warning)
                        self.warnings.append(warning)

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
        if line[self.indexes['ean13']] and check_ean(line[self.indexes['ean13']]):
            vals['ean13'] = line[self.indexes['ean13']]
        else:
            return {'rejection': 'Product {!s} rejected because EAN is invalid.'.format(line[self.indexes['ean13']])}


        # Determine the category
        # ----------------------
        if line[self.indexes['first_category']+8]:
            vals['categ_id'] = line[self.indexes['first_category']+8]
        elif line[self.indexes['first_category']+6]:
            vals['categ_id'] = line[self.indexes['first_category']+6]
        elif line[self.indexes['first_category']+4]:
            vals['categ_id'] = line[self.indexes['first_category']+4]
        elif line[self.indexes['first_category']+2]:
            vals['categ_id'] = line[self.indexes['first_category']+2]
        elif line[self.indexes['first_category']]:
            vals['categ_id'] = line[self.indexes['first_category']]
        else:
            return {'rejection': 'Product {!s} rejected because category is not provided.'.format(vals['ean13'])}


        vals['categ_id'] = next((x['id'] for x in self.categories if x['code'] == vals['categ_id']),None)
        if not vals['categ_id']:
            return {'rejection': 'Product {!s} rejected because category is unknown.'.format(vals['ean13'])}


        vals['name'] = line[self.indexes['name']].capitalize()
        if not vals['name']:
            return {'rejection': 'Product {!s} rejected because name could not be determined.'.format(vals['ean13'])}



        # THR product code
        # ----------------
        supplier = {}
        supplier['name'] = self.thr
        supplier['min_qty'] = 1
        supplier['product_code'] = line[self.indexes['product_code']]
        vals['seller_ids'] =  [(0, False, supplier)]

        # Images
        # ------
        vals['images'] = []
        for image in line[self.indexes['first_image']:self.indexes['first_image']+10]:
            if image:
                vals['images'].append([0,False,{'supplier' : self.thr, 'url':image}])


        # Properties
        # ----------
        vals['properties'] = []
        for i, prop in enumerate(line):
            if i <= self.indexes['recommended_price'] or not prop:
                continue
            new_prop = {}
            new_prop['name'] = next((x['id'] for x in self.properties if x['name'] == self.header[i]),None)
            if not new_prop['name']:
                continue
            new_prop['value'] = prop.capitalize()
            vals['properties'].append([0,False,new_prop])


        vals['short_description'] = line[self.indexes['name']]
        vals['description'] = line[self.indexes['long_description']] or ''
        vals['procure_method'] = 'make_to_order'
        vals['type'] = 'product'
        vals['state'] = 'draft'
        vals['recommended_price'] = line[self.indexes['recommended_price']]
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
        image_db = self.pool.get('webdust.image')


        if line[self.indexes['name']]:
            vals['name'] = line[self.indexes['name']].capitalize()

        # Determine the category
        # ----------------------
        if line[self.indexes['first_category']+8]:
            vals['categ_id'] = line[self.indexes['first_category']+8]
        elif line[self.indexes['first_category']+6]:
            vals['categ_id'] = line[self.indexes['first_category']+6]
        elif line[self.indexes['first_category']+4]:
            vals['categ_id'] = line[self.indexes['first_category']+4]
        elif line[self.indexes['first_category']+2]:
            vals['categ_id'] = line[self.indexes['first_category']+2]
        elif line[self.indexes['first_category']]:
            vals['categ_id'] = line[self.indexes['first_category']]

        if 'categ_id' in vals:
            vals['categ_id'] = next((x['id'] for x in self.categories if x['code'] == vals['categ_id']),None)
        if vals['categ_id'] == product['categ_id'][0]:
            del vals['categ_id']

        # THR product code
        # ----------------
        sellers = supplier_db.read(cr, uid, product['seller_ids'])
        seller = next((x for x in sellers if x['name'][0] == self.thr),None)
        if not seller:
            supplier = {}
            supplier['name'] = self.thr
            supplier['min_qty'] = 1
            supplier['product_code'] = line[self.indexes['product_code']]
            vals['seller_ids'] =  [(0, False, supplier)]
        else:
            if seller['product_code'] != line[0]:
                supplier_db.write(cr, uid, seller['id'], {'product_code' : line[self.indexes['product_code']]}, context=None)

        # Images
        # ------
        image_ids = image_db.search(cr, uid, [('product_id','=',product['id']),('supplier','=',self.thr)])
        if image_ids: image_db.unlink(cr, uid, image_ids)
        vals['images'] = []
        for image in line[self.indexes['first_image']:self.indexes['first_image']+10]:
            if image:
                vals['images'].append([0,False,{'supplier' : self.thr, 'url':image}])



        # Properties
        # ----------
        vals['properties'] = []
        properties = prop_db.read(cr, uid, product['properties'])
        for i, prop in enumerate(line):
            if i <= self.indexes['recommended_price'] or not prop:
                continue
            prop_id = next((x['id'] for x in self.properties if x['name'] == self.header[i]),None)
            if not prop_id:
                continue
            property = next((x for x in properties if x['name'][0] == prop_id),None)
            if not property:
                new_prop = {}
                new_prop['value'] = prop.capitalize()
                new_prop['name'] = prop_id
                vals['properties'].append([0,False,new_prop])
            else:
                if property['value'] != prop.capitalize():
                    prop_db.write(cr, uid, property['id'], {'value' : prop.capitalize()}, context=None)
        if not vals['properties']:
            del vals['properties']


        vals['short_description'] = line[self.indexes['name']]
        vals['description'] = line[self.indexes['long_description']] or ''
        vals['recommended_price'] = line[self.indexes['recommended_price']]
        return {'id' : self.write(cr, uid, [product['id']], vals, context=None)}

















