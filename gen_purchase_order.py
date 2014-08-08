from openerp.osv import osv,fields
from openerp.tools.translate import _
from openerp import netsvc
from itertools import groupby
import logging
import json
import requests
import datetime
import time

#       +-------------------------+     +-------------------+
#       |  push_quotations_manual |     |  push_quotations  |
#       |-------------------------|     |-------------------|
#       |    pushes a # of ids    |     | calls MRP run     |
#       |    (from tree view)     |     | gathers ids of new|
#       |                         |     | docs              |
#       +-------------+-----------+     | (from scheduler)  |
#                     |                 +---------+---------+
#                     |                           |
#                     |                           |
#                     +---------------------------+
#                     |
#          +----------+----------+
#          |     push_several    |       +--------------------+
#          |---------------------|       |     push_single    |
#          | validate customizing|       |--------------------|
#          | test connection     |       | convert to JSON    |
#          | loop quotations     +-------> actually push      |
#          |                     |       | create log EDI doc |
#          +---------------------+       +--------------------+

class purchase_order(osv.Model):
    _name = "purchase.order"
    _inherit = "purchase.order"


    def _function_quotation_sent_get(self, cr, uid, ids, field, arg, context=None):
        edi_db = self.pool.get('clubit.tools.edi.document.outgoing')
        model_db = self.pool.get('ir.model.data')
        flow_id = model_db.search(cr, uid, [('name', '=', 'edi_thr_purchase_order_out'), ('model','=','clubit.tools.edi.flow')])
        if not flow_id: return False
        flow_id = model_db.browse(cr, uid, flow_id)[0]
        flow_id = flow_id.res_id

        res = dict.fromkeys(ids, False)
        for po in self.browse(cr, uid, ids, context=context):
            docids = edi_db.search(cr, uid, [('flow_id', '=', flow_id),('reference', '=', po.partner_ref)])
            if not docids: continue
            edi_docs = edi_db.browse(cr, uid, docids, context=context)
            edi_docs.sort(key = lambda x: x.create_date, reverse=True)
            res[po.id] = edi_docs[0].create_date
        return res


    _columns = {
        'quotation_sent_at': fields.function(_function_quotation_sent_get, type='datetime', string='Quotation sent at'),
        'auto_edi_allowed': fields.boolean('Allow auto EDI sending'),
        'create_date':fields.datetime('Creation date'), #added so we can use it in the model
    }


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

    def create(self, cr, uid, vals, context=None):
        ''' purchase.order:create()
        ---------------------------
        This method is overwritten to make sure auto_edi_allowed
        is marked as true, *if* the PO is made using the MRP scheduler.
        --------------------------------------------------------------- '''
        if context:
            if 'mrp_scheduler' in context:
                vals['auto_edi_allowed'] = True

        if vals['origin']:
            sale_db = self.pool.get('sale.order')
            sale_order = sale_db.search(cr, uid, [('name','=',vals['origin'])])
            if sale_order:
                sale_order = sale_db.read(cr, uid, sale_order, ['desired_delivery_date'], context=context)[0]
                if sale_order['desired_delivery_date']:
                    for i, line in enumerate(vals['order_line']):
                        line[2]['date_planned'] = sale_order['desired_delivery_date']
        return super(purchase_order, self).create(cr, uid, vals, context)


    def write(self, cr, uid, ids, vals, context=None):
        if context:
            if 'mrp_scheduler' in context:
                vals['auto_edi_allowed'] = True
        return super(purchase_order, self).write(cr, uid,ids, vals, context)

    def copy(self, cr, uid, id, default=None, context=None):
        ''' purchase.order:copy_data
            ------------------------
            The partner reference and auto edi cannot be copied during a duplication
            ------------------------------------------------------------------------ '''
        default['partner_ref'] = False
        default['auto_edi_allowed'] = False
        return super(purchase_order, self).copy(cr, uid, id, default, context)


    def push_quotations_manual(self, cr, uid, ids):
        ''' purchase.order:push_quotations_manual()
        --------------------------------------------
        This method is used by the PO selection view to send or resend
        quotations as EDI messages.
        -------------------------------------------------------------- '''
        orders = self.browse(cr, uid, ids)
        if orders: return self.push_several(cr, uid, orders)
        return False


    def push_quotations(self, cr, uid):
        ''' purchase.order:push_quotations()
        ------------------------------------
        This method is used as a scheduler to automatically run
        the MRP scheduler (to make sure PO's are properly merged) and then
        handle the EDI processing. Eligible documents are sent using a REST
        service. The response to this request is handled in a different
        scheduler due to asynchronous processing.
        ------------------------------------------------------------------- '''

        log = logging.getLogger(None)
        log.info('QUOTATION_PUSHER: Starting processing on the quotation pusher.')
        proc_db = self.pool.get('procurement.order')

        # Run the MRP Scheduler
        # ---------------------
        log.info('QUOTATION_PUSHER: Running the standard MRP scheduler.')
        proc_db.run_scheduler(cr, uid, False, True)


        # Search for documents that need to be sent, also throw out quotations
        # that have already been sent before
        # --------------------------------------------------------------------
        log.info('QUOTATION_PUSHER: Searching for quotations to send.')
        pids = self.search(cr, uid, [('state', '=', 'draft'), ('auto_edi_allowed','=', True)])
        if not pids:
            log.info('QUOTATION_PUSHER: No quotations found. Processing is done.')
            return True
        orders = self.browse(cr, uid, pids)
        orders = [x for x in orders if not x.quotation_sent_at]
        if not pids:
            log.info('QUOTATION_PUSHER: No quotations found. Processing is done.')
            return True

        log.info('QUOTATION_PUSHER: Sending the following POs: {!s}'.format(str(pids)))
        return self.push_several(cr, uid, orders)


    def push_several(self, cr, uid, orders):

        log = logging.getLogger(None)
        helpdesk_db = self.pool.get('crm.helpdesk')

        # Group the orders by partner so each EDI flow only has to run once
        # -----------------------------------------------------------------
        for partner, group in groupby(orders, lambda x: x.partner_id):

                log.info('QUOTATION_PUSHER: Pushing quotations for {!s}'.format(partner.name))

                # Does this partner listen to an outgoing PO EDI flow?
                # ----------------------------------------------------
                flow = [x for x in partner.edi_flows if x.flow_id.model == 'purchase.order' and x.flow_id.direction == 'out']
                if not flow:
                    log.info('QUOTATION_PUSHER: {!s} did not have a processing method(), skipping partner'.format(partner.name))
                    continue

                # Call the EDI method for this flow
                # ---------------------------------
                method = getattr(self, flow[0].flow_id.method)
                if not method:
                    log.info('QUOTATION_PUSHER: {!s} did not have a processing method(), skipping partner'.format(partner.name))
                    continue

                try:
                    method(cr, uid, group)
                except Exception as e:
                    log.warning('QUOTATION_PUSHER: A serious error occurred during processing for partner {!s}'.format(partner.name))
                    helpdesk_db.create_simple_case(cr, uid, 'A serious error occurred in pushSeveral trying to call the EDI method.', str(e))
        cr.commit()
        return True



    def push_several_thr(self, cr, uid, orders):

        log = logging.getLogger(None)
        helpdesk_db = self.pool.get('crm.helpdesk')

        # Make sure the required customizing is present
        # ---------------------------------------------
        settings = self.pool.get('clubit.tools.settings').get_settings(cr, uid)
        rest_info = [x for x in settings.connections if x.name == 'THR_REST_PO' and x.is_active == True]
        if not rest_info:
            log.warning('QUOTATION_PUSHER: Could not find the THR_REST_PO connection settings, creating CRM helpdesk case.')
            helpdesk_db.create_simple_case(cr, uid, 'An error occurred during the MRP/EDI Quotation pusher.', 'Missing THR_REST_PO connection in the EDI settings')
            cr.commit()
            return True
        rest_info = rest_info[0]

        http_info = [x for x in settings.connections if x.name == 'HTTP_EDI_SERVER' and x.is_active == True]
        if not http_info:
            log.warning('QUOTATION_PUSHER: Could not find the HTTP_EDI_SERVER connection settings, creating CRM helpdesk case.')
            helpdesk_db.create_simple_case(cr, uid, 'An error occurred during the MRP/EDI Quotation pusher.', 'Missing HTTP_EDI_SERVER connection in the EDI settings')
            cr.commit()
            return True
        http_info = http_info[0]

        # Test if the website is up, no need to hog resources otherwise
        # -------------------------------------------------------------
        log.info('QUOTATION_PUSHER: Polling if connection is available.')
        try:
            requests.head(rest_info.url, timeout = 10)
        except Exception as e:
            log.warning('QUOTATION_PUSHER: Connection is not available! Creating a helpdesk case and aborting process.')
            helpdesk_db.create_simple_case(cr, uid, 'MRP/EDI Quotation pusher: connection is down.',
                                                    'Could not connect to {!s}, cannot push quotations! \nError given is {!s}'.format(rest_info.url, str(e)))
            cr.commit()
            return True



        # Process every quotation
        # -----------------------
        for order in orders:

            # Check if there's an open helpdesk case for this order.
            # If so, don't try to send it.
            # ------------------------------------------------------

            case = False
            hids = helpdesk_db.search(cr, uid, [('ref', '=', 'purchase.order,{!s}'.format(str(order.id)))])
            if hids:
                case = helpdesk_db.browse(cr, uid, hids[0])
                if case.state != 'done':
                    log.info('QUOTATION_PUSHER: Skipping quotation {!s} because it has an open helpdesk case.'.format(order.name))
                    continue

            # Push this order
            # ---------------
            log.info('QUOTATION_PUSHER: Pushing quotation {!s}.'.format(order.name))
            self.push_single_thr(cr, uid, order, rest_info, http_info, case)

        cr.commit()
        log.info('QUOTATION_PUSHER: Processing is done.')
        return True



    def push_single_thr(self, cr, uid, order, connection, http_connection, case = None):
        ''' purchase.order:push_single()
        --------------------------------
        This method pushes a quotation to the given connection.
        In case the quotation is older than 1 hour and we don't get a response
        or the site is down, a helpdesk case is created or reopened.
        ---------------------------------------------------------------------- '''

        helpdesk_db = self.pool.get('crm.helpdesk')
        log = logging.getLogger(None)
        now = datetime.datetime.now()
        created_at = datetime.datetime.strptime(order.create_date, '%Y-%m-%d %H:%M:%S')
        error = False

        # Convert the quotation to JSON and push it
        # -----------------------------------------
        content = self.edi_export(cr, uid, order)
        content['urlCallback'] = ''.join([http_connection.url, 'purchaseorder?reference=', order.partner_ref])
        try:
            response = requests.put(connection.url, headers={'content-type': 'application/json'}, data=json.dumps(content), auth=(connection.user, connection.password))
            if response.status_code != 200:
                error = 'QUOTATION_PUSHER: Quotation {!s} was not sent. HTTP code {!s} received with response: {!s}'.format(order.name, response.status_code, response.content)
                log.warning(error)
            else:
                response_content = json.loads(response.content)

                if 'status' not in response_content or 'orderId' not in response_content:
                    error = 'QUOTATION_PUSHER: Quotation {!s} was sent, but received a response that didnt tell us the status: {!s}'.format(order.name, response.content)
                    log.warning(error)
                elif response_content['status'] != '1':
                    error = 'QUOTATION_PUSHER: Quotation {!s} was sent, but it was rejected, response: {!s}'.format(order.name, response.content)
                    log.warning(error)
                else:
                    log.info('QUOTATION_PUSHER: Quotation {!s} was sent successfully.'.format(order.name))
                    self.create_outgoing_edi_document(cr, uid, content)
                    return True

        except ValueError as e:
            error = 'QUOTATION_PUSHER: Quotation {!s} was sent, but the response was not valid JSON. Response: {!s}.'.format(order.name, response.content)
            log.warning(error)
        except Exception as e:
            error = str(e)

        # If the code reaches this point, it means something went wrong
        # -------------------------------------------------------------
        log.warning('QUOTATION_PUSHER: Quotation {!s} was not sent. Error given was: {!s}'.format(order.name, error))
        if created_at + datetime.timedelta(0,900)  < now:
            if not case:
                helpdesk_db.create_simple_case(cr, uid, 'Quotation {!s} has been open for longer than 15 minutes.'.format(order.name), error, 'purchase.order,{!s}'.format(str(order.id)))
            else:
                case.write({'description': error})
                helpdesk_db.case_reset(cr, uid, [case.id])
        return True


    def pull(self, cr, uid, order, connection):
        ''' purchase.order:pull()
        -------------------------
        This method pulls the most recent data from THR.
        ------------------------------------------------ '''

        try:
            response = requests.get('/'.join([connection.url,order.partner_ref]), auth=(connection.user, connection.password))
            if response.status_code == 200:
                return response.content
            else:
                return False

        except Exception as e:
            return False

        return True



    def edi_export(self, cr, uid, po, context=None):
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
            'supplierReference' : po.partner_ref,
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
                'quantity'      : int(line.product_qty),
                'unitPrice'     : line.price_unit,
                'positionPrice' : line.price_subtotal,
            }

            edi_doc['orderPositions'].append(edi_line)

        # Return the result
        # -----------------
        return edi_doc





    def edi_import_validator(self, cr, uid, ids, context):
        ''' purchase.order:edi_import_validator()
            -------------------------------------
            This method will perform a validation on the provided
            EDI Document on a logical & functional level.
            ----------------------------------------------------- '''

        # Read the EDI Document
        # ---------------------
        edi_db = self.pool.get('clubit.tools.edi.document.incoming')
        product_db = self.pool.get('product.product')
        document = edi_db.browse(cr, uid, ids, context)

        # Convert the document to JSON
        # ----------------------------
        try:
            data = json.loads(document.content)
            if not data:
                edi_db.message_post(cr, uid, document.id, body='Error found: EDI Document is empty.')
                return self.resolve_helpdesk_case(cr, uid, document)
        except Exception:
            edi_db.message_post(cr, uid, document.id, body='Error found: content is not valid JSON.')
            return self.resolve_helpdesk_case(cr, uid, document)

        # Check if the supplierReference is provided and exists
        # -----------------------------------------------------
        reference = data['order'].get('supplierReference', False)
        if not reference:
            edi_db.message_post(cr, uid, document.id, body='Error found: supplierReference is not provided.')
            return self.resolve_helpdesk_case(cr, uid, document)

        order_id = self.search(cr, uid, [('partner_ref','=', reference)])
        if not order_id:
            edi_db.message_post(cr, uid, document.id, body='Error found: supplierReference {!s} is unknown.'.format(reference))
            return self.resolve_helpdesk_case(cr, uid, document)
        order = self.browse(cr, uid, order_id[0])


        # Validate the document now that it contains the most recent data
        # ---------------------------------------------------------------
        if not data.get('orderId', False):
            edi_db.message_post(cr, uid, document.id, body='Error found: orderId (at root level) missing in this document.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if not data.get('status', False):
            edi_db.message_post(cr, uid, document.id, body='Error found: status (at root level) missing in this document.')
            return self.resolve_helpdesk_case(cr, uid, document)


        details = data.get('order', False)
        if not details:
            edi_db.message_post(cr, uid, document.id, body='Error found: No order details provided in this document.')
            return self.resolve_helpdesk_case(cr, uid, document)

        if not details.get('amountTotal', False):
            edi_db.message_post(cr, uid, document.id, body='Error found: amountTotal missing in this document.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if not details.get('orderID', False):
            edi_db.message_post(cr, uid, document.id, body='Error found: orderID missing in this document.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if not details.get('supplierReference', False):
            edi_db.message_post(cr, uid, document.id, body='Error found: supplierReference missing in this document.')
            return self.resolve_helpdesk_case(cr, uid, document)

        if not details.get('shippingAddress', False):
            edi_db.message_post(cr, uid, document.id, body='Error found: shippingAddress missing in this document.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if len(details['shippingAddress']) != 2:
            edi_db.message_post(cr, uid, document.id, body='Error found: shippingAddress should contain exactly 2 elements.')
            return self.resolve_helpdesk_case(cr, uid, document)

        if not details.get('orderPositions', False):
            edi_db.message_post(cr, uid, document.id, body='Error found: orderPositions missing in this document.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if len(details['orderPositions']) == 0:
            edi_db.message_post(cr, uid, document.id, body='Error found: orderPositions missing in this document.')
            return self.resolve_helpdesk_case(cr, uid, document)


        for i, line in enumerate(details['orderPositions']):
            if not line.get('articleNumber', False):
                edi_db.message_post(cr, uid, document.id, body='Error found: line item at index {!s} did not have an articleNumber.'.format(str(i)))
                return self.resolve_helpdesk_case(cr, uid, document)
            if not line.get('articlePrice', False):
                edi_db.message_post(cr, uid, document.id, body='Error found: line item at index {!s} did not have an articlePrice.'.format(str(i)))
                return self.resolve_helpdesk_case(cr, uid, document)
            if not line.get('quantity', False):
                edi_db.message_post(cr, uid, document.id, body='Error found: line item at index {!s} did not have an quantity.'.format(str(i)))
                return self.resolve_helpdesk_case(cr, uid, document)

            product = product_db.search(cr, uid, [('ean13', '=', line['articleNumber'])])
            if not product:
                edi_db.message_post(cr, uid, document.id, body='Error found: line item at index {!s} had an unknown articleNumber (ean).'.format(str(i)))
                return self.resolve_helpdesk_case(cr, uid, document)

            if not [x for x in order.order_line if x.product_id.ean13 == line['articleNumber']]:
                edi_db.message_post(cr, uid, document.id, body='Error found: line item at index {!s} had an articleNumber (ean) that was not part of the quotation!'.format(str(i)))
                return self.resolve_helpdesk_case(cr, uid, document)


        # If we get all the way to here, the document is valid
        # ----------------------------------------------------
        return True



    def edi_import_thr(self, cr, uid, ids, context):
        ''' purchase.order:edi_import_thr()
        -----------------------------------
        This method will perform the actual import of the
        provided EDI Document.
        ------------------------------------------------- '''

        # Attempt to validate the file right before processing
        # ----------------------------------------------------
        edi_db = self.pool.get('clubit.tools.edi.document.incoming')
        if not self.edi_import_validator(cr, uid, ids, context):
            edi_db.message_post(cr, uid, ids, body='Error found: during processing, the document was found invalid.')
            return False


        # Process the EDI Document
        # ------------------------
        document = edi_db.browse(cr, uid, ids, context)
        name = self.process_incoming_thr_document(cr, uid, document, context)
        if not name:
            edi_db.message_post(cr, uid, ids, body='Error found: something went wrong while updating the quotation.')
            return False
        else:
            edi_db.message_post(cr, uid, ids, body='Quotation {!s} converted to a Purchase Order.'.format(name))
            return True



    def process_incoming_thr_document(self, cr, uid, document, context):
        ''' purchase.order:process_incoming_thr_document()
        --------------------------------------------------
        This method will adjust and validate the quotation
        regardless of what THR said they can deliver.
        -------------------------------------------------- '''

        try:
            data = json.loads(document.content)
        except Exception:
            return False

        order = self.search(cr, uid, [('partner_ref', '=', data['order']['supplierReference'])])
        if not order: return False
        order = self.browse(cr, uid, order[0])

        # Confirm the purchase order, regardless of what THR says
        # -------------------------------------------------------
        wf_service = netsvc.LocalService('workflow')
        wf_service.trg_validate(uid, 'purchase.order', order.id, 'purchase_confirm', cr)
        return order.name


        # The confirmation of the PO should have lead to the creation of an incoming shipment
        # We're now going to receive this incoming shipment according to what THR provided us.
        # In case of shortages, this should automatically create a backorder for easier tracking.
        # ---------------------------------------------------------------------------------------
        shipment_db = self.pool.get('stock.picking.in')
        shipment = shipment_db.search(cr, uid, [('purchase_id', '=', order.id)])
        if not shipment:
            return False

        vals = {}
        for order_line in order.order_line:
            line = [x for x in data['order']['orderPositions'] if x['articleNumber'] == order_line.product_id.ean13]
            move = {'prodlot_id': False, 'product_id': order_line.product_id.id, 'product_uom': order_line.product_uom.id}
            if line:
                move['product_qty'] = line['quantity']
                vals["move" + str(line.id)] = move

        # Make the call to do_partial() to set the document to 'done'
        # -----------------------------------------------------------
        try:
            shipment_db.do_partial(cr, uid, [shipment.id], vals, context)
        except Exception:
            return False

        # Actually create the sale order
        # ------------------------------
        return order.name




    def create_outgoing_edi_document(self, cr, uid, content):

        edi_db = self.pool.get('clubit.tools.edi.document.outgoing')
        partner_id = self.pool.get('res.partner').search(cr, uid, [('name', '=', 'THR')])


        # Find the correct EDI flow
        # -------------------------
        model_db = self.pool.get('ir.model.data')
        flow_id = model_db.search(cr, uid, [('name', '=', 'edi_thr_purchase_order_out'), ('model','=','clubit.tools.edi.flow')])
        if not flow_id: return False
        flow_id = model_db.browse(cr, uid, flow_id)[0]
        flow_id = flow_id.res_id

        # Create the document
        # -------------------
        values = {
            'name'       : content['supplierReference'],
            'reference'  : content['supplierReference'],
            'partner_id' : partner_id[0],
            'flow_id'    : flow_id,
            'content'    : json.dumps(content),
            'state'      : 'new',
            'location'   : 'null',
        }

        edi_db.create(cr, uid, values)




    def resolve_helpdesk_case(self, cr, uid, document):

        helpdesk_db = self.pool.get('crm.helpdesk')
        case = helpdesk_db.search(cr, uid, [('ref','=','{!s},{!s}'.format(document._table_name, document.id))])
        if case:
            case = helpdesk_db.browse(cr, uid, case[0])
            if case.state == 'done':
                helpdesk_db.case_reset(cr, uid, [case.id])

        if not case:
            vals = {
                'partner_id' : document.partner_id.id,
                'user_id'    : uid,
                'ref'        : '{!s},{!s}'.format(document._table_name, document.id),
                'name'       : 'Manual action required for EDI document #{!s}'.format(document.name)
            }
            case = helpdesk_db.create(cr, uid, vals)
            case = helpdesk_db.browse(cr, uid, case)

        return False






