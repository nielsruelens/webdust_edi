from openerp.osv import osv
from openerp.tools.translate import _
import csv, StringIO
import threading
from itertools import chain
from openerp import pooler

class product(osv.Model):

    _name = "product.product"
    _inherit = 'product.product'
    _description = "Product extensions"


    def edi_import_locations(self, cr, uid, ids, context):
        ''' product.product:edi_import_locations()
        ------------------------------------------
        This method handles the location import for a given vendor.
        ----------------------------------------------------------- '''

        # Make sure the settings are defined
        # ----------------------------------
        edi_db = self.pool.get('clubit.tools.edi.document.incoming')
        self.settings = self.pool.get('clubit.tools.settings').get_settings(cr, uid)
        if not self.settings:
            edi_db.message_post(cr, uid, ids, body='Could not start the location upload, missing EDI settings.')
            return False

        # Process the EDI Document
        # ------------------------
        document = edi_db.browse(cr, uid, ids, context)
        self.log.info('UPLOAD-LOCATIONS: Starting the location upload for supplier {!s}.'.format(document.partner_id.name))

        content = []
        dummy_file = StringIO.StringIO(document.content)
        reader = csv.reader(dummy_file, delimiter=';', quotechar='"')
        for row in reader:
            content.append(row)

        del content[0] #throw out the header, don't need it

        result = self.upload_locations(cr, uid, document.partner_id, content, context)
        self.log.info('UPLOAD-LOCATIONS: Location upload is complete for supplier {!s}.'.format(document.partner_id.name))

        if result:
            edi_db.message_post(cr, uid, ids, body='<br/>'.join(list(chain(*result))))
            warning = '\n'.join(list(chain(*result)))
            self.pool.get('crm.helpdesk').create_simple_case(cr, uid, 'These warnings generated during the THR location upload need to be validated.', warning)
        return True






    def upload_locations(self, cr, uid, supplier, content=[], context=None):
        ''' product.product:upload_locations()
            ----------------------------------
            This method is the root process node
            for the location upload for a given supplier.
            --------------------------------------------- '''

        if not content or not supplier:
            return False


        # Fix all EAN codes, might be a couple missing leading zeroes
        # Reason this is done beforehand is because we want to be
        # able to search for all existing products in 1 go, see below.
        # ------------------------------------------------------------
        self.log.info('UPLOAD-LOCATIONS: checking if all the EAN codes are 13 chars long.')
        for i, line in enumerate(content):
            if len(line[0]) < 13:
                warning = 'UPLOAD-LOCATIONS: adding missing leading zeroes to EAN {!s}'.format(line[0])
                self.log.warning(warning)
                self.warnings.append(warning)
                line[0] = '0' * (13-len(line[0])) + line[0]


        # Split the actual processing of the content into
        # several threads to hopefully speed up performance
        # -------------------------------------------------
        threads = []
        results = [None] * self.settings.no_of_processes
        for i in xrange(self.settings.no_of_processes):
            start = len(content) / self.settings.no_of_processes * i
            end = len(content) / self.settings.no_of_processes * (i+1)
            if i+1 == self.settings.no_of_processes: end = len(content)
            t = threading.Thread(target=self._content_thread_locations, args=(cr, uid, supplier, content[start:end], results, i, context))
            threads.append(t)
            t.start()

        self.log.info('UPLOAD-LOCATIONS: Waiting till all threads have finished.')
        for t in threads:
            t.join()
        self.log.info('UPLOAD-LOCATIONS: All threads have finished.')
        return results




    def _content_thread_locations(self, cr, uid, supplier, content, results, index, context=None):
        ''' product.product:_content_thread_locations()
        -----------------------------------------------
        This method is called by upload_locations()
        several times in a multi threaded context to speed up
        processing for several tens of thousand products.
        Based on the records it receives, it will attempt to
        create or update location information of products.
        ------------------------------------------------------ '''

        results[index] = []

        # Create a new cursor for this thread
        # -----------------------------------
        new_cr = pooler.get_db(cr.dbname).cursor()

        try:

            # Get all the ids + content for all the products that already exist.
            # ------------------------------------------------------------------
            self.log.info('UPLOAD-LOCATIONS: reading products.')
            prod_ids = self.search(new_cr, uid, [('ean13', 'in', [ x[0] for x in content ])])
            products = self.read(new_cr, uid, prod_ids, ['id', 'ean13'], context=context)


            # Process all the products
            # ------------------------
            for i, line in enumerate(content):
                i = i + 1


                # Make sure the product actually exists in OpenERP
                # ------------------------------------------------
                self.log.info('UPLOAD-LOCATIONS: processing product with EAN {!s} ({!s} of {!s})'.format(line[0], i, len(content)))
                product = next((x for x in products if x['ean13'] == line[0]), None)
                if not product:
                    string = 'UPLOAD-LOCATIONS: location provided for ean {!s} but the product is not defined in OpenERP.'.format(line[0])
                    self.log.warning(string)
                    results[index].append(string)
                    continue

                # Commit every 200 products to make sure
                # lost work in case of problems is limited
                # ----------------------------------------
                if i % 200 == 0:
                    new_cr.commit()


                # Add the location data
                # ---------------------
                self.write(new_cr, uid, [product['id']], {'supplier_storage_location':line[1]}, context=None)

            new_cr.commit()
        finally:
            new_cr.close()
        return False










