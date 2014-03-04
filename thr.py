from openerp.osv import osv
from openerp.tools.translate import _
from os.path import join
from os import path
import csv
import logging

class product(osv.Model):

    _name = "product.product"
    _inherit = 'product.product'
    _description = "Product extensions"

    log = logging.getLogger(None)


    def upload_thr(self, cr, uid, param=None, context=None):

        self.log.info('UPLOAD_THR: starting the THR masterdata upload')

        # Find the file
        # -------------
        root_path = join('EDI', cr.dbname, 'THR_product_upload')
        self.log.info('UPLOAD_THR: attempting to open folder {!s}'.format(root_path))
        if not path.exists(root_path):
            self.log.error('UPLOAD_THR: could not open folder {!s}'.format(root_path))
            return False
        root_path = join(root_path, 'export_pim_handig.csv')

        # Read the file
        # -------------
        content = []
        self.log.info('UPLOAD_THR: attempting to open file {!s}'.format(root_path))
        with open(root_path, 'rb') as csvfile:
            reader = csv.reader(csvfile, delimiter=',', quotechar='"')
            for row in reader:
                content.append(row)

        no_of_processes = 4
        if param and param['no_of_processes'] > 0:
            no_of_processes = param['no_of_processes']

        # Process the categories, exclude the header
        # ------------------------------------------
        if not param or param['load_categories']:
            cat_db = self.pool.get('product.category')
            cat_db.upload_thr(cr, uid, [ x[2:12] for x in content[1:] ], no_of_processes=no_of_processes, context=context)


        # Process the properties
        # ----------------------
        if not param or param['load_properties']:
            prop_db = self.pool.get('webdust.property')
            prop_db.upload_thr(cr, uid, content[0], context=context)


        # Process the products
        # --------------------
        if not param or param['load_products']:
            prod_db = self.pool.get('product.product')
            prod_db.upload_thr_detail(cr, uid, content, no_of_processes=no_of_processes, context=context)

        self.log.info('UPLOAD_THR: masterdata upload complete.')
        return True












