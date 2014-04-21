from openerp.osv import osv
from openerp.tools.translate import _
import logging
import netsvc

class product(osv.Model):

    _name = "product.product"
    _inherit = 'product.product'
    _description = "All THR uploads combined into one"

    def upload_thr_product_combined(self, cr, uid, context=None):
        ''' product.product:upload_thr_product_combined()
        -------------------------------------------------
        This method combines all THR product related uploads
        into one process to reduce manual operations needed
        and spare processing cycles.
        ---------------------------------------------------- '''

        edi_db = self.pool.get('clubit.tools.edi.document.incoming')
        model_db = self.pool.get('ir.model.data')
        wf_service = netsvc.LocalService("workflow")


        # Load the masterdata
        # -------------------
        self.log.info('UPLOAD_THR-COMBINED: starting on the masterdata.')
        param = {}
        param['load_categories'] = True
        param['load_properties'] = True
        param['load_products']   = True
        self.upload_thr_master_from_file(cr, uid, param, context)
        self.log.info('UPLOAD_THR-COMBINED: masterdata upload is complete.')

        # Load the availability
        # ---------------------
        (flow_id,) = model_db.search(cr, uid,[('name','=','edi_thr_product_availability_in')])
        flow = model_db.browse(cr, uid, flow_id)
        flow_id = flow.res_id
        doc_ids = edi_db.search(cr, uid,[('flow_id','=',flow_id),('state','=','new')])
        if doc_ids:
            self.log.info('UPLOAD_THR-COMBINED: availability EDI docs found, pushing them to ready.')
            for doc_id in doc_ids:
                wf_service.trg_validate(uid, 'clubit.tools.edi.document.incoming', doc_id, 'button_to_ready', cr)
            cr.commit()
        else:
            self.log.info('UPLOAD_THR-COMBINED: no availability EDI docs found, skipping.')

        self.log.info('UPLOAD_THR-COMBINED: combined upload is complete.')
        return True














