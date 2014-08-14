from openerp.osv import osv
from os.path import join
from os import path, makedirs
import json

class webdust_edi_post_install(osv.TransientModel):
    _name = "webdust.edi.post.install"


    def get_flow_id(self, cr, uid, name):
        model_db = self.pool.get('ir.model.data')
        (flow_id,) = model_db.search(cr, uid,[('name','=',name)])
        flow = model_db.browse(cr, uid, flow_id)
        return flow.res_id



    def finalize_installation(self, cr, context=None):

        partner_db = self.pool.get('res.partner')
        model_db = self.pool.get('ir.model.data')

        # Make sure the THR EDI folders exist
        # -----------------------------------
        mypath = join('EDI', cr.dbname, 'THR_product_upload')
        if not path.exists(mypath): makedirs(mypath)
        mypath = join(mypath, 'processed')
        if not path.exists(mypath): makedirs(mypath)

        # Configure the handig.nl partner for all EDI flows
        # -------------------------------------------------
        partner = partner_db.search(cr, 1, [('name','=','handig.nl')])
        if partner:
            partner = partner_db.browse(cr, 1, partner[0])
            if not partner.edi_flows:
                flow = self.get_flow_id(cr, 1, 'edi_spree_sale_order_in')
                if flow: partner_db.write(cr, 1, [partner.id], {'edi_relevant':True, 'edi_flows': [[0,False,{'flow_id' : flow, 'partnerflow_active':True}]]})

            # Give the handig.nl partner the correct external identifier
            external = model_db.search(cr, 1, [('name','=','webdust_handig_nl')])
            if not external:
                model_db.create(cr, 1, {'module': 'webdust_edi_manual', 'name':'webdust_handig_nl', 'model':'res.partner', 'res_id':partner.id})


        # Configure the THR partner for all EDI flows
        # -------------------------------------------
        partner = partner_db.search(cr, 1, [('name','=','THR')])
        if partner:
            partner = partner_db.browse(cr, 1, partner[0])
            if not partner.edi_flows:
                vals = {'edi_flows':[]}
                flow = self.get_flow_id(cr, 1, 'edi_thr_product_master_in')
                if flow: vals['edi_flows'].append([0,False,{'flow_id' : flow, 'partnerflow_active':True}])

                flow = self.get_flow_id(cr, 1, 'edi_thr_product_pricing_in')
                if flow: vals['edi_flows'].append([0,False,{'flow_id' : flow, 'partnerflow_active':True}])

                flow = self.get_flow_id(cr, 1, 'edi_thr_product_availability_in')
                if flow: vals['edi_flows'].append([0,False,{'flow_id' : flow, 'partnerflow_active':True}])

                flow = self.get_flow_id(cr, 1, 'edi_thr_product_location_in')
                if flow: vals['edi_flows'].append([0,False,{'flow_id' : flow, 'partnerflow_active':True}])

                flow = self.get_flow_id(cr, 1, 'edi_thr_purchase_order_out')
                if flow: vals['edi_flows'].append([0,False,{'flow_id' : flow, 'partnerflow_active':True}])

                flow = self.get_flow_id(cr, 1, 'edi_thr_purchase_order_in')
                if flow: vals['edi_flows'].append([0,False,{'flow_id' : flow, 'partnerflow_active':True}])

                partner_db.write(cr, 1, [partner.id], vals)

            # Give the handig.nl partner the correct external identifier
            external = model_db.search(cr, 1, [('name','=','webdust_thr')])
            if not external:
                model_db.create(cr, 1, {'module': 'webdust_edi_manual', 'name':'webdust_thr', 'model':'res.partner', 'res_id':partner.id})

        return True






