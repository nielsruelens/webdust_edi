from openerp.osv import osv
from openerp.tools.translate import _
from os.path import join
from os import path
import csv, json, StringIO
import logging

class product(osv.Model):

    _name = "product.product"
    _inherit = 'product.product'
    _description = "Product extensions"

    log = logging.getLogger(None)


    def read_thr_master_flow_id(self, cr, uid):
        ''' product.product:read_thr_master_flow_id()
            -----------------------------------------
            This method reads and returns the flow id
            for the reimport EDI flow (masterdata THR).
            ------------------------------------------- '''
        model_db = self.pool.get('ir.model.data')
        (flow_id,) = model_db.search(cr, uid,[('name','=','clubit_tools_edi_flow_5')])
        flow = model_db.browse(cr, uid, flow_id)
        return flow.res_id


    def read_thr_file(self, cr, uid, f):
        ''' product.product:read_thr_file()
            -------------------------------
            This method reads and returns the content
            of a given file.
            ----------------------------------------- '''
        content = []
        self.log.info('UPLOAD_THR: attempting to open file {!s}'.format(f))
        with open(f, 'rb') as csvfile:
            reader = csv.reader(csvfile, delimiter=',', quotechar='"')
            for row in reader:
                content.append(row)
        return content



    def upload_thr_master_from_file(self, cr, uid, param=None, context=None):
        ''' product.product:upload_thr_master_from_file()
        -------------------------------------------------
        This method handles a THR product import based on a file.
        It is meant to be called from wizard product_upload_thr.
        It will create an EDI flow document for all records that
        went into error.
        ---------------------------------------------------- '''

        # Find the file
        # -------------
        root_path = join('EDI', cr.dbname, 'THR_product_upload')
        self.log.info('UPLOAD_THR: attempting to open folder {!s}'.format(root_path))
        if not path.exists(root_path):
            self.log.error('UPLOAD_THR: could not open folder {!s}'.format(root_path))
            return False
        root_path = join(root_path, 'export_pim_handig.csv')

        # Read the file and send it for processing
        # ----------------------------------------
        content = self.read_thr_file(cr, uid, root_path)

        param['do_supplier_removal'] = True
        self.upload_thr_master(cr, uid, param, content, context)

        # If errors occurred, they will be stored in attribute self.result
        # see thr_products.py
        # ----------------------------------------------------------------
        if self.invalid:
            self.log.info('UPLOAD_THR: Errors occurred during masterdata upload, performing cleanup.')
            self.invalid.insert(0, self.header) #add the header line to this list
            flow_id = self.read_thr_master_flow_id(cr, uid)
            edi_db = self.pool.get('clubit.tools.edi.document')
            self.log.info('UPLOAD_THR: Creating EDI document to hold erroneous lines.')
            edi_db.position_document(cr, uid, self.thr, flow_id, self.invalid, content_type='csv')
            self.log.info('UPLOAD_THR: Cleanup done.')

        cr.commit()
        return True




    def edi_import_thr(self, cr, uid, ids, context):
        ''' product.product:edi_import_thr()
        ------------------------------------
        This method handles a THR product import document.
        These documents are generated in case there are any
        errors in the standard import interface and are used
        to have an overview of everything that went wrong.
        ---------------------------------------------------- '''

        # Process the EDI Document
        # ------------------------
        edi_db = self.pool.get('clubit.tools.edi.document.incoming')
        document = edi_db.browse(cr, uid, ids, context)

        content = []
        dummy_file = StringIO.StringIO(document.content)
        reader = csv.reader(dummy_file, delimiter=',', quotechar='"')
        for row in reader:
            content.append(row)

        param = {'do_supplier_removal':False, 'no_of_processes':1, 'load_categories':True, 'load_properties':True, 'load_products':True}
        self.upload_thr_master(cr, uid, param, content, context)
        if self.invalid:
            edi_db.message_post(cr, uid, ids, body='Error found: something went wrong while creating this set of products, check the server log.')
            return False

        return True









    def upload_thr_master(self, cr, uid, param=None, content=[], context=None):
        ''' product.product:upload_thr_master()
            -----------------------------------
            This method is the root process node for the
            THR master data upload. It is called both by
            the stand-alone upload wizard and the EDI flow.
            ----------------------------------------------- '''

        self.clear_globals(cr, uid)
        if not content:
            self.log.info('UPLOAD_THR: masterdata upload complete.')
            return True

        no_of_processes = 2
        if param and param['no_of_processes'] > 0:
            no_of_processes = param['no_of_processes']


        do_supplier_removal = True
        if param and 'do_supplier_removal' in param:
            do_supplier_removal = param['do_supplier_removal']


        # Process the categories, exclude the header
        # ------------------------------------------
        if not param or param['load_categories']:
            cat_db = self.pool.get('product.category')
            cat_db.upload_thr(cr, uid, [ x[2:12] for x in content[1:] ], context=context)


        # Process the properties
        # ----------------------
        if not param or param['load_properties']:
            prop_db = self.pool.get('webdust.property')
            prop_db.upload_thr(cr, uid, content[0], context=context)


        # Process the products
        # --------------------
        if not param or param['load_products']:
            prod_db = self.pool.get('product.product')
            prod_db.upload_thr_master_detail(cr, uid, content, no_of_processes=no_of_processes, do_supplier_removal=do_supplier_removal, context=context)

        self.log.info('UPLOAD_THR: masterdata upload complete.')
        return True












