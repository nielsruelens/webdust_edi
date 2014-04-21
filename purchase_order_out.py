from openerp.osv import osv,fields
from openerp.tools.translate import _


class purchase_order(osv.Model):
    _name = "purchase.order"
    _inherit = "purchase.order"


    ''' purchase.order:_function_edi_sent_get()
        --------------------------------------
        This method calculates the value of field edi_sent by
        looking at the database and checking for EDI docs
        on this purchase order.
        ------------------------------------------------------ '''
    def _function_edi_sent_get(self, cr, uid, ids, field, arg, context=None):
        edi_db = self.pool.get('clubit.tools.edi.document.outgoing')
        flow_db = self.pool.get('clubit.tools.edi.flow')
        flow_id = flow_db.search(cr, uid, [('model', '=', 'purchase.order'),('method', '=', 'send_edi_out')])[0]
        res = dict.fromkeys(ids, False)
        for po in self.browse(cr, uid, ids, context=context):
            docids = edi_db.search(cr, uid, [('flow_id', '=', flow_id),('reference', '=', po.name)])
            if not docids: continue
            edi_docs = edi_db.browse(cr, uid, docids, context=context)
            edi_docs.sort(key = lambda x: x.create_date, reverse=True)
            res[po.id] = edi_docs[0].create_date
        return res


    _columns = {
        'edi_sent': fields.function(_function_edi_sent_get, type='datetime', string='EDI sent'),
    }





    ''' purchase.order:edi_partner_resolver()
        -------------------------------------
        This method attempts to find the correct partner
        to whom we should send an EDI document for a
        number of PO's.
        ------------------------------------------------ '''
    def edi_partner_resolver(self, cr, uid, ids, context):

        result_list = []
        for pick in self.browse(cr, uid, ids, context):
            result_list.append({'id' : pick.id, 'partner_id': pick.partner_id.id})
        return result_list







    ''' purchase.order:send_edi_out()
        -----------------------------
        This method will perform the export of a purchase
        order, the simple version. Only PO's that
        are in state 'draft' may be passed to this
        method, otherwise an error will occur.
        ------------------------------------------------- '''
    def send_edi_out(self, cr, uid, items, context=None):


        edi_db = self.pool.get('clubit.tools.edi.document.outgoing')

        # Get the selected items
        # ----------------------
        purchases = [x['id'] for x in items]
        purchases = self.browse(cr, uid, purchases, context=context)


        # Loop over all purchases to check if their
        # collective states allow for EDI processing
        # ------------------------------------------
        nope = ""
        for po in purchases:
            if po.state != 'draft':
                nope += po.name + ', '
        if nope:
            raise osv.except_osv(_('Warning!'), _("Not all documents had states 'draft'. Please exclude the following documents: {!s}").format(nope))


        # Actual processing of all the purchases
        # --------------------------------------
        for po in purchases:
            content = self.edi_export(cr, uid, po, None, context)
            partner_id = [x['partner_id'] for x in items if x['id'] == po.id][0]
            result = edi_db.create_from_content(cr, uid, po.name, content, partner_id, 'purchase.order', 'send_edi_out')
            if result != True:
                raise osv.except_osv(_('Error!'), _("Something went wrong while trying to create one of the EDI documents. Please contact your system administrator. Error given: {!s}").format(result))




    ''' purchase.order:edi_export()
        ---------------------------
        This method parses a given object to a JSON
        EDI structure.
        ------------------------------------------- '''
    def edi_export(self, cr, uid, po, edi_struct=None, context=None):

        # Instantiate variables
        # ---------------------
        edi_doc = {}
        partner_db = self.pool.get('res.partner')
        product_db = self.pool.get('product.product')
        info_db = self.pool.get('product.supplierinfo')

        partner = partner_db.browse(cr, uid, po.partner_id.id, context)

        # Header fields
        # -------------
        edi_doc['name']               = po.name
        edi_doc['supplier']           = partner.name
        edi_doc['supplier_order_ref'] = po.partner_ref
        edi_doc['order_date']         = po.date_order
        edi_doc['client_order_ref']   = po.origin
        edi_doc['expected_date']      = po.minimum_planned_date
        edi_doc['validated_by']       = True
        edi_doc['date_approved']      = True
        edi_doc['amount_untaxed']     = po.amount_untaxed
        edi_doc['comment']            = po.notes

        # Line items
        # ----------
        edi_doc['lines'] = []
        for line in po.order_line:
            edi_line = {}
            product = product_db.browse(cr, uid, line.product_id.id, context)

            # determine the product reference (default or supplier)
            edi_line['product_ref'] = product.default_code
            info_ids = info_db.search(cr, uid, [('name', '=', po.partner_id.id),('product_id', '=', product.id)], context=context)
            if info_ids:
                info = info_db.browse(cr, uid, info_ids, context)[0]
                if info and info.product_code:
                    edi_line['product_ref'] = info.product_code

            edi_line['line_no']       = line.id
            edi_line['product_name']  = product.name
            edi_line['product_ean13'] = product.ean13
            edi_line['line_qty']      = line.product_qty
            edi_line['unit_price']    = line.price_unit
            edi_line['line_price']    = line.price_subtotal
            edi_doc['validated_by']   = True
            edi_doc['date_approved']  = True

            edi_doc['lines'].append(edi_line)

        # Return the result
        # -----------------
        return edi_doc












