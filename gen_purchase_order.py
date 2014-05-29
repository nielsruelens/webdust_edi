from openerp.osv import osv,fields
from openerp.tools.translate import _

class purchase_order(osv.Model):
    _name = "purchase.order"
    _inherit = "purchase.order"


# Dead code, but keeping it anyways
# MRP logic is way more complex than this
#    def create(self, cr, uid, vals, context=None):
#        ''' purchase.order:create()
#        ---------------------------
#        This method is overwritten to make sure the correct
#        partner is chosen. The default MRP logic simply chooses
#        the first partner, not the cheapest, fastest, ...
#        ------------------------------------------------------- '''
#
#        # Only execute the custom code if we're in the MPR process
#        # --------------------------------------------------------
#        stack = inspect.stack()
#        if stack[1][3] == 'create_procurement_purchase_order':
#            supplier = self.determine_ideal_partner(cr, uid, vals)
#            vals['partner_id'] = supplier.name.id
#            vals['order_line'][0][2]['price_unit'] = supplier.default_price
#
#        return super(purchase_order, self).create(cr, uid, vals, context)
#
#
#    def determine_ideal_partner(self, cr, uid, vals):
#        ''' purchase.order:determine_ideal_partner()
#        --------------------------------------------
#        Given a set of values that will become a PO, this method
#        determines the ideal partner in case "lowest price" is
#        chosen for the product.
#        -------------------------------------------------------- '''
#
#        prod_db = self.pool.get('product.product')
#        product = prod_db.browse(cr, uid, vals['order_line'][0][2]['product_id'] )
#        if product.cost_method != 'lowest':
#            return vals['partner_id']
#
#        lowest_supplier = False
#        for supplier in product.seller_ids:
#            if supplier.state == 'unavailable': continue
#            if not lowest_supplier:
#                lowest_supplier = supplier
#                continue
#            if supplier.default_price < lowest_supplier.default_price:
#                lowest_supplier = supplier
#
#        return lowest_supplier


    def auto_edi_out(self, cr, uid):
        ''' purchase.order:auto_edi_out()
        ---------------------------------
        This method is used as a scheduler to automatically run
        the MRP scheduler (to make sure PO's are properly merged) and then
        send EDI messages for the resulting quotations. An EDI document is
        only sent once.
        ------------------------------------------------------------------ '''

        proc_db = self.pool.get('procurement.order')
        flow_db = self.pool.get('clubit.tools.edi.flow')
        edi_db = self.pool.get('clubit.tools.edi.wizard.outgoing')

        # Run the MRP Scheduler
        # ---------------------
        proc_db.run_scheduler(cr, uid, False, True)

        # Automatically send EDI documents
        # --------------------------------
        flow_id = flow_db.search(cr, uid, [('model', '=', 'purchase.order'),('method','=','send_edi_out')])
        if not flow_id:
            return False

        pids = self.search(cr, uid, [('state', '=', 'draft')])
        orders = self.browse(cr, uid, pids)
        pids = [x.id for x in orders if not x.edi_sent]
        if not pids:
            return True

        context = {
            'active_ids': pids,
            'active_model': 'purchase.order',
            'flow_id': flow_id[0],
        }
        edi_db.resolve(cr, uid, pids, context)
        return True



    def _function_edi_sent_get(self, cr, uid, ids, field, arg, context=None):
        ''' purchase.order:_function_edi_sent_get()
        -------------------------------------------
        This method calculates the value of field edi_sent by
        looking at the database and checking for EDI docs
        on this purchase order.
        ------------------------------------------------------ '''
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





    def edi_partner_resolver(self, cr, uid, ids, context):
        ''' purchase.order:edi_partner_resolver()
        -----------------------------------------
        This method attempts to find the correct partner
        to whom we should send an EDI document for a
        number of PO's.
        ------------------------------------------------ '''
        result_list = []
        for pick in self.browse(cr, uid, ids, context):
            result_list.append({'id' : pick.id, 'partner_id': pick.partner_id.id})
        return result_list







    def send_edi_out(self, cr, uid, items, context=None):
        ''' purchase.order:send_edi_out()
        ---------------------------------
        This method will perform the export of a purchase
        order, the simple version. Only PO's that
        are in state 'draft' may be passed to this
        method, otherwise an error will occur.
        ------------------------------------------------- '''
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




    def edi_export(self, cr, uid, po, edi_struct=None, context=None):
        ''' purchase.order:edi_export()
        -------------------------------
        This method parses a given object to a JSON
        EDI structure.
        ------------------------------------------- '''

        # Lookup the sale order
        # ---------------------
        sale_db = self.pool.get('sale.order')
        sale_order = sale_db.search(cr, uid, [('name','=', po.origin)])
        if sale_order:
            sale_order = sale_db.browse(cr, uid, sale_order[0])


        # Header fields
        # -------------
        edi_doc = {
            'shopID'            : '1',
            'resellerID'        : '1',
            'supplierReference' : po.name,
            'shipmentProvider'  : 'GLS',
            'deliveryMethod'    : '1',
            'amountUntaxed'     : po.amount_untaxed,
            'amountTotal'       : po.amount_total,
            'expectedDate'      : po.minimum_planned_date,
            'scheduledDate'     : po.minimum_planned_date,
            'orderDate'         : po.date_order,
            'orderPositions'    : [],
        }

        # If there is a sale order, attach customer info
        if sale_order:
            street = sale_order.partner_id.street
            if sale_order.partner_id.street2:
                street = ' '.join([street,sale_order.partner_id.street2])
            edi_doc['shippingAddress'] = {
                'name'        : sale_order.partner_id.name,
                'street'      : street,
                'postalcode'  : sale_order.partner_id.zip,
                'city'        : sale_order.partner_id.city,
                'country'     : sale_order.partner_id.country_id.code,
                'phone'       : sale_order.partner_id.phone,
                'mobilephone' : sale_order.partner_id.mobile,
                'email'       : sale_order.partner_id.email,
            }

            # If the customer is a company, add the following information
            if sale_order.partner_id.parent_id:
                edi_doc['shippingAddress']['company'] = sale_order.partner_id.parent_id.name
                edi_doc['shippingAddress']['vat']     = sale_order.partner_id.parent_id.vat



        # Line items
        # ----------
        for line in po.order_line:

            edi_line = {
                'positionID'    : line.id,
                'articleNumber' : line.product_id.ean13,
                'articleName'   : line.product_id.name,
                'quantity'      : line.product_qty,
                'unitPrice'     : line.price_unit,
                'positionPrice' : line.price_subtotal,
            }

            edi_doc['orderPositions'].append(edi_line)

        # Return the result
        # -----------------
        return edi_doc












