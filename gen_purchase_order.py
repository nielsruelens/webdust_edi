from openerp.osv import osv,fields
from openerp.tools.translate import _
import logging
import json, requests, datetime

class purchase_order(osv.Model):
    _name = "purchase.order"
    _inherit = "purchase.order"

    _columns = {
        'quotation_sent_at': fields.datetime('Quotation sent at', readonly=True),
        'auto_edi_allowed': fields.boolean('Allow auto EDI sending'),
        'create_date':fields.datetime('Creation date'), #added so we can use it in the model
    }

    _PUSH_CODE = 'PUSH_ERROR'

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
        helpdesk_db = self.pool.get('crm.helpdesk')

        # Run the MRP Scheduler
        # ---------------------
        log.info('QUOTATION_PUSHER: Running the standard MRP scheduler.')
        proc_db.run_scheduler(cr, uid, False, True)



        # Make sure the required customizing is present
        # ---------------------------------------------
        settings = self.pool.get('clubit.tools.settings').get_settings(cr, uid)
        rest_info = [x for x in settings.connections if x.name == 'THR_REST_PO']
        if not rest_info:
            log.warning('QUOTATION_PUSHER: Could not find the THR_REST_PO connection settings, creating CRM helpdesk case.')
            helpdesk_db.create_simple_case(cr, uid, 'An error occurred during the MRP/EDI Quotation pusher.', 'Missing THR_REST_PO connection in the EDI settings')
            cr.commit()
            return True
        rest_info = rest_info[0]

        http_info = [x for x in settings.connections if x.name == 'HTTP_EDI_SERVER']
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


        # Search for documents that need to be sent
        # -----------------------------------------
        log.info('QUOTATION_PUSHER: Searching for quotations to send.')
        pids = self.search(cr, uid, [('state', '=', 'draft'), ('quotation_sent_at', '=', False)])
        if not pids:
            log.info('QUOTATION_PUSHER: No quotations found. Processing is done.')
            return True

        log.info('QUOTATION_PUSHER: Sending the following POs: {!s}'.format(str(pids)))
        orders = self.browse(cr, uid, pids)


        # Process every quotation
        # -----------------------
        for order in orders:

            # Check if there's an open helpdesk case for this order.
            # If so, don't try to send it.
            # ------------------------------------------------------

            case = False
            hids = helpdesk_db.search(cr, uid, [('ref', '=', 'purchase.order,{!s}'.format(str(order.id))), ('description','=', self._PUSH_CODE)])
            if hids:
                case = helpdesk_db.browse(cr, uid, hids[0])
                if case.state != 'done':
                    log.info('QUOTATION_PUSHER: Skipping quotation {!s} because it has an open helpdesk case.'.format(order.name))
                    continue

            # Push this order
            # ---------------
            log.info('QUOTATION_PUSHER: Pushing quotation {!s}.'.format(order.name))
            self.push(cr, uid, order, rest_info, http_info, case)

        cr.commit()
        log.info('QUOTATION_PUSHER: Processing is done.')
        return True



    def push(self, cr, uid, order, connection, http_connection, case = None):
        ''' purchase.order:push()
        -------------------------
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
        content['urlCallback'] = ''.join([http_connection.url, 'purchaseOrder'])
        try:
            response = requests.put(connection.url, headers={'content-type': 'application/json'}, data=json.dumps(content), auth=(connection.user, connection.password))
            if response.status_code == 200:
                log.info('QUOTATION_PUSHER: Quotation {!s} was sent successfully.'.format(order.name))
                self.write(cr, uid, order.id, {'quotation_sent_at': now})
                self.create_outgoing_edi_document(cr, uid, content)
                return True
            else:
                error = response.status_code

        except Exception as e:
            error = str(e)

        # If the code reaches this point, it means something went wrong
        # -------------------------------------------------------------
        log.warning('QUOTATION_PUSHER: Quotation {!s} was not sent. Error given was: {!s}'.format(order.name, error))
        if created_at + datetime.timedelta(0,3600)  < now:
            if not case:
                helpdesk_db.create_simple_case(cr, uid, 'Quotation {!s} has been open for longer than an hour.'.format(order.name), self._PUSH_CODE, 'purchase.order,{!s}'.format(str(order.id)))
            else:
                helpdesk_db.case_reset(cr, uid, [case.id])
        return True


    def pull(self, cr, uid, order, connection):
        ''' purchase.order:pull()
        -------------------------
        This method pulls the most recent data from THR.
        ------------------------------------------------ '''

        try:
            response = requests.get('/'.join([connection.url,order.name]), auth=(connection.user, connection.password))
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
        if 'supplierReference' not in data:
            edi_db.message_post(cr, uid, document.id, body='Error found: supplierReference is not provided.')
            return self.resolve_helpdesk_case(cr, uid, document)

        order_id = self.search(cr, uid, [('name','=', data['supplierReference'])])
        if not order_id:
            edi_db.message_post(cr, uid, document.id, body='Error found: supplierReference {!s} is unknown.'.format(data['supplierReference']))
            return self.resolve_helpdesk_case(cr, uid, document)
        order = self.browse(cr, uid, order_id[0])

        # Since THR doesn't give us all the data, we need to enrich this EDI document by pulling the latest version
        # ---------------------------------------------------------------------------------------------------------
        settings = self.pool.get('clubit.tools.settings').get_settings(cr, uid)
        rest_info = [x for x in settings.connections if x.name == 'THR_REST_PO']
        if not rest_info:
            edi_db.message_post(cr, uid, document.id, body='Error found: THR_REST_PO service is missing in our customizing!')
            return self.resolve_helpdesk_case(cr, uid, document)
        rest_info = rest_info[0]

        # Actually perform the pull
        # -------------------------
        result = self.pull(cr, uid, order, rest_info)
        if result == False:
            edi_db.message_post(cr, uid, document.id, body='Error occurred: could not pull the latest data from THR.')
            return self.resolve_helpdesk_case(cr, uid, document)
        else:
            try:
                data = json.loads(result)
                if not data:
                    edi_db.message_post(cr, uid, document.id, body='Error found: EDI Document is empty.')
                    return self.resolve_helpdesk_case(cr, uid, document)
            except Exception:
                edi_db.message_post(cr, uid, document.id, body='Error found: content is not valid JSON.')
                return self.resolve_helpdesk_case(cr, uid, document)
        edi_db.write(cr, uid, document.id, {'content' : result})




        # Validate the document now that it contains the most recent data
        # ---------------------------------------------------------------
        if 'line_items' not in data:
            edi_db.message_post(cr, uid, document.id, body='Error found: No line items provided in this document.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if len(data['line_items']) == 0:
            edi_db.message_post(cr, uid, document.id, body='Error found: No line items provided in this document.')
            return self.resolve_helpdesk_case(cr, uid, document)

        for line in data['line_items']:
            if 'price' not in line:
                edi_db.message_post(cr, uid, document.id, body='Error found: line item with id {!s} did not have a price.'.format(line['id']))
                return self.resolve_helpdesk_case(cr, uid, document)
            if line['price'] == 0:
                edi_db.message_post(cr, uid, document.id, body='Error found: line item with id {!s} did not have a price.'.format(line['id']))
                return self.resolve_helpdesk_case(cr, uid, document)

            if 'variant' not in line:
                edi_db.message_post(cr, uid, document.id, body='Error found: line item with id {!s} did not structure "variant".'.format(line['id']))
                return self.resolve_helpdesk_case(cr, uid, document)
            if 'sku' not in line['variant']:
                edi_db.message_post(cr, uid, document.id, body='Error found: line item with id {!s} did not have field "variant:sku (ean code)".'.format(line['id']))
                return self.resolve_helpdesk_case(cr, uid, document)
            if not line['variant']['sku']:
                edi_db.message_post(cr, uid, document.id, body='Error found: line item with id {!s} did have an ean code.'.format(line['id']))
                return self.resolve_helpdesk_case(cr, uid, document)

            product = product_db.search(cr, uid, [('ean13', '=', line['variant']['sku'])])
            if not product:
                edi_db.message_post(cr, uid, document.id, body='Error found: line item with id {!s} had an unknown ean code.'.format(line['id']))
                return self.resolve_helpdesk_case(cr, uid, document)
            product = product_db.browse(cr, uid, product[0])
            if not product.sale_ok:
                edi_db.message_post(cr, uid, document.id, body='Error found: line item with id {!s} had an article that cannot be sold.'.format(line['id']))
                return self.resolve_helpdesk_case(cr, uid, document)


        # If we get all the way to here, the document is valid
        # ----------------------------------------------------
        return True



    def edi_import_spree(self, cr, uid, ids, context):
        ''' purchase.order:edi_import_spree()
        -------------------------------------
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
        name = self.process_edi_document(cr, uid, document, context)
        if not name:
            edi_db.message_post(cr, uid, ids, body='Error found: something went wrong while creating the sale order.')
            return False
        else:
            edi_db.message_post(cr, uid, ids, body='Sale order {!s} created'.format(name))
            return True



    def process_edi_document(self, cr, uid, document, context):
        ''' purchase.order:create_sale_order_spree()
        --------------------------------------------
        This method will create a sales order based
        on the provided EDI input.
        ------------------------------------------- '''

        product_db = self.pool.get('product.product')
        ir_model_db = self.pool.get('ir.model.data')
        edi_db = self.pool.get('clubit.tools.edi.document.incoming')

        # Check if the customer already exists, create it if it doesn't
        # -------------------------------------------------------------
        data = json.loads(document.content)
        customer, message = self.resolve_customer(cr, uid, document.partner_id, data['bill_address'], data['email'])
        if not customer:
            edi_db.message_post(cr, uid, document.id, body='Error during processing: {!s}'.format(message))
            return self.resolve_helpdesk_case(cr, uid, document)

        payment = False
        if data['payment_state'] == 'balance_due':
            payment = ir_model_db.search(cr, uid, [('name','=', 'edi_payment_term2'), ('model', '=', 'account.payment.term')])
        elif data['payment_state'] == 'pending':
            payment = ir_model_db.search(cr, uid, [('name','=', 'edi_payment_term1'), ('model', '=', 'account.payment.term')])
        if payment:
            payment = ir_model_db.browse(cr, uid, payment[0]).res_id


        # Prepare the call to create a sale order
        # ---------------------------------------
        vals = {
            'partner_id'          : customer.id,
            'partner_shipping_id' : customer.id,
            'partner_invoice_id'  : customer.id,
            'pricelist_id'        : customer.property_product_pricelist.id,
            'origin'              : data['number'],
            'date_order'          : data['created_at'][0:10],
            'payment_term'        : payment,
            'order_line'          : [],
            'picking_policy'      : 'one',
            'order_policy'        : 'picking'
        }


        for line in data['line_items']:

            product = product_db.search(cr, uid, [('ean13', '=', line['variant']['sku'])])
            product = product_db.browse(cr, uid, product[0])

            detail = {
                'product_uos_qty' : line['quantity'],
                'product_uom_qty' : line['quantity'],
                'product_id'      : product.id,
                'type'            : product.procure_method,
                'price_unit'      : line['price'],
                'name'            : line['variant']['name'],
                'th_weight'       : product.weight * line['quantity'],
                'tax_id'          : [[6, False, self.pool.get('account.fiscal.position').map_tax(cr, uid, customer.property_account_position, product.taxes_id)   ]],
            }

            order_line = []
            order_line.extend([0])
            order_line.extend([False])
            order_line.append(detail)
            vals['order_line'].append(order_line)


        # Actually create the sale order
        # ------------------------------
        order = self.create(cr, uid, vals, context=None)
        if not order:
            edi_db.message_post(cr, uid, document.id, body='Error during processing: could not create the sale order, unknown reason.')
            return self.resolve_helpdesk_case(cr, uid, document)
        self.action_button_confirm(cr, uid, [order])
        order = self.browse(cr, uid, order)
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
            'content'    : content,
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






