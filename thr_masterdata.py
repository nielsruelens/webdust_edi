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
    thr = False
    settings = False


    def read_thr_partner(self, cr, uid):
        (self.thr,) = self.pool.get('res.partner').search(cr, uid, [('name', '=', 'THR')])



    def read_thr_master_flow_id(self, cr, uid):
        ''' product.product:read_thr_master_flow_id()
            -----------------------------------------
            This method reads and returns the flow id
            for the reimport EDI flow (masterdata THR).
            ------------------------------------------- '''
        model_db = self.pool.get('ir.model.data')
        (flow_id,) = model_db.search(cr, uid,[('name','=','edi_thr_product_master_in')])
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

    def validate_thr_file(self, cr, uid, content):

        self.log.error('UPLOAD_THR: Validating file...')
        check = ['ProductID',
                 'EANcode',
                 'Classificatie Niveau 1',
                 'Classificatie Niveau 2',
                 'Classificatie Niveau 3',
                 'Classificatie Niveau 4',
                 'Classificatie Niveau 5',
                 'Classificatie Niveau 1 omschrijving',
                 'Classificatie Niveau 2 omschrijving',
                 'Classificatie Niveau 3 omschrijving',
                 'Classificatie Niveau 4 omschrijving',
                 'Classificatie Niveau 5 omschrijving',
                 'Korte Omschrijving',
                 'Lange Omschrijving',
                 'Bestand Afbeelding 1',
                 'Bestand Afbeelding 2',
                 'Bestand Afbeelding 3',
                 'Bestand Afbeelding 4',
                 'Bestand Afbeelding 5',
                 'Bestand Afbeelding 6',
                 'Bestand Afbeelding 7',
                 'Bestand Afbeelding 8',
                 'Bestand Afbeelding 9',
                 'Bestand Afbeelding 10',
                 'Consumentenadviesprijs (incl)',
                 ]

        ok = True
        for x in check:
            if x not in content[0]:
                self.log.error('UPLOAD_THR: could not find column: {!s}'.format(x))
                ok = False
        return ok


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
        if not self.validate_thr_file(cr, uid, content):
            self.log.info('UPLOAD_THR: The file contained structural errors, aborting process.')
            return False


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

        param = {'load_categories':True, 'load_properties':True, 'load_products':True}
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
            self.log.info('UPLOAD_THR: no content provided to process.')
            return True

        self.settings = self.pool.get('clubit.tools.settings').get_settings(cr, uid)
        if not self.settings:
            self.log.warning('UPLOAD_THR: could not load EDI settings, aborting process.')
            return True

        # Process the categories, exclude the header
        # Find the index of the 1st category column
        # ------------------------------------------
        if not param or param['load_categories']:
            cat_db = self.pool.get('product.category')
            i = content[0].index('Classificatie Niveau 1')
            cat_db.upload_thr(cr, uid, [ x[i:i+10] for x in content[1:] ], context=context)


        # Process the properties
        # Find the index of the 1st property column
        # -----------------------------------------
        if not param or param['load_properties']:
            prop_db = self.pool.get('webdust.property')
            i = content[0].index('Bestand Afbeelding 10')+1
            prop_db.upload_thr(cr, uid, content[0][i:], context=context)


        # Process the products
        # --------------------
        if not param or param['load_products']:
            self.upload_thr_master_detail(cr, uid, content, context=context)

        self.log.info('UPLOAD_THR: masterdata upload complete.')
        return True












