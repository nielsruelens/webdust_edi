from openerp.osv import osv, fields
import json, datetime, time
from openerp.tools.translate import _


class sale_order(osv.Model):
    _name = "sale.order"
    _inherit = "sale.order"

    _columns = {
        'desired_delivery_date': fields.datetime('Desired Delivery Date'),
    }


    def edi_import_validator(self, cr, uid, ids, context):
        ''' sale.order:edi_import_validator()
            ---------------------------------
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


        if 'number' not in data:
            edi_db.message_post(cr, uid, document.id, body='Error found: No number provided.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if self.search(cr, uid, [('client_order_ref', '=', data['number'])]):
            edi_db.message_post(cr, uid, document.id, body='Error found: number has already been imported.')
            return self.resolve_helpdesk_case(cr, uid, document)


        # Check if the minimum amount of customer information is provided
        # ---------------------------------------------------------------
        if 'email' not in data:
            edi_db.message_post(cr, uid, document.id, body='Error found: No email provided.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if not data['email']:
            edi_db.message_post(cr, uid, document.id, body='Error found: No email provided.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if 'bill_address' not in data:
            edi_db.message_post(cr, uid, document.id, body='Error found: bill_address structure is missing (our customer).')
            return self.resolve_helpdesk_case(cr, uid, document)
        if 'full_name' not in data['bill_address']:
            edi_db.message_post(cr, uid, document.id, body='Error found: customer name was missing @ bill_address:full_name.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if not data['bill_address']['full_name']:
            edi_db.message_post(cr, uid, document.id, body='Error found: customer name was missing @ bill_address:full_name.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if 'address1' not in data['bill_address']:
            edi_db.message_post(cr, uid, document.id, body='Error found: customer address was missing @ bill_address:address1.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if not data['bill_address']['address1']:
            edi_db.message_post(cr, uid, document.id, body='Error found: customer address was missing @ bill_address:address1.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if 'city' not in data['bill_address']:
            edi_db.message_post(cr, uid, document.id, body='Error found: customer city was missing @ bill_address:city.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if not data['bill_address']['city']:
            edi_db.message_post(cr, uid, document.id, body='Error found: customer city was missing @ bill_address:city.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if 'zipcode' not in data['bill_address']:
            edi_db.message_post(cr, uid, document.id, body='Error found: customer zipcode was missing @ bill_address:zipcode.')
            return self.resolve_helpdesk_case(cr, uid, document)
        if not data['bill_address']['zipcode']:
            edi_db.message_post(cr, uid, document.id, body='Error found: customer zipcode was missing @ bill_address:zipcode.')
            return self.resolve_helpdesk_case(cr, uid, document)



        # Validate the line items from this document
        # ------------------------------------------
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
        ''' sale.order:edi_import_spree()
        ---------------------------------
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
        name = self.create_sale_order_spree(cr, uid, document, context)
        if not name:
            edi_db.message_post(cr, uid, ids, body='Error found: something went wrong while creating the sale order.')
            return False
        else:
            edi_db.message_post(cr, uid, ids, body='Sale order {!s} created'.format(name))
            return True








    def create_sale_order_spree(self, cr, uid, document, context):
        ''' sale.order:create_sale_order_spree()
        ----------------------------------------
        This method will create a sales order based
        on the provided EDI input.
        ------------------------------------------- '''

        product_db = self.pool.get('product.product')
        ir_model_db = self.pool.get('ir.model.data')
        edi_db = self.pool.get('clubit.tools.edi.document.incoming')

        # Check if the customer already exists, create it if it doesn't
        # -------------------------------------------------------------
        data = json.loads(document.content)
        billing_partner, shipping_partner = self.resolve_customer_info(cr, uid, data['bill_address'], data['ship_address'], data['email'])
        if not billing_partner or not shipping_partner:
            edi_db.message_post(cr, uid, document.id, body='Error during processing: could not find/create a billing/shipping partner')
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
            'partner_id'          : shipping_partner.id,
            'partner_shipping_id' : shipping_partner.id,
            'partner_invoice_id'  : billing_partner.id,
            'pricelist_id'        : shipping_partner.property_product_pricelist.id,
            'client_order_ref'    : data['number'],
            'date_order'          : data['completed_at'][0:10],
            'payment_term'        : payment,
            'order_line'          : [],
            'picking_policy'      : 'one',
            'order_policy'        : 'picking'
        }

        today = datetime.datetime.now()
        desired = today+datetime.timedelta(days=2)
        if 'customer_delivery_date' in data and data['customer_delivery_date']:
            desiredTemp = time.strptime(data['customer_delivery_date'][0:10], '%Y-%m-%d')
            desiredTemp = datetime.datetime.fromtimestamp(time.mktime(desired))
            desired = desired.replace(desiredTemp.year, desiredTemp.month, desiredTemp.day)
        vals['desired_delivery_date'] = desired.strftime('%Y-%m-%d %H:%M:%S')


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
                'delay'           : (desired - today).days,
                'tax_id'          : [[6, False, self.pool.get('account.fiscal.position').map_tax(cr, uid, shipping_partner.property_account_position, product.taxes_id)   ]],
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






    def resolve_customer_info(self, cr, uid, billing_address, shipping_address, email):

        partner_db = self.pool.get('res.partner')
        country_db = self.pool.get('res.country')

        # Check if this partner already exists
        # ------------------------------------
        billing_partner = partner_db.search(cr, uid, [('email', '=', email), ('parent_id','=',False)])
        if billing_partner:
            billing_partner = partner_db.browse(cr, uid, billing_partner[0])

            # Check if the shipment address exists
            # ------------------------------------
            country_id = country_db.search(cr, uid, [('code', '=', shipping_address['country']['iso'])])
            shipping_partner = False
            partner_ids = partner_db.search(cr, uid, [('parent_id','=',billing_partner.id)])
            if partner_ids:
                for partner in partner_db.browse(cr, uid, partner_ids):
                    if partner.name == shipping_address['full_name'] and partner.city == shipping_address['city'] and partner.zip == shipping_address['zipcode'] and partner.street == shipping_address['address1'] and partner.street2 == shipping_address['address2'] and partner.country_id.id == country_id[0]:
                        shipping_partner = partner

            if shipping_partner:
                return billing_partner, shipping_partner





        # If the billing address doesn't exist yet, create it
        # ----------------------------------------------------
        if not billing_partner:
            country_id = country_db.search(cr, uid, [('code', '=', billing_address['country']['iso'])])
            vals = {
                'active'     : True,
                'customer'   : True,
                'is_company' : False,
                'city'       : billing_address['city'],
                'zip'        : billing_address['zipcode'],
                'street'     : billing_address['address1'],
                'street2'    : billing_address['address2'],
                'country_id' : country_id[0],
                'email'      : email,
                'mobile'     : billing_address['phone'],
                'phone'      : billing_address['alternative_phone'],
                'name'       : billing_address['full_name'],
            }

            billing_partner = partner_db.create(cr, uid, vals)
            billing_partner = partner_db.browse(cr, uid, billing_partner)


        # If the shipping address doesn't exist yet, create it
        # ----------------------------------------------------
        country_id = country_db.search(cr, uid, [('code', '=', shipping_address['country']['iso'])])
        vals = {
            'active'     : True,
            'customer'   : True,
            'is_company' : False,
            'city'       : shipping_address['city'],
            'zip'        : shipping_address['zipcode'],
            'street'     : shipping_address['address1'],
            'street2'    : shipping_address['address2'],
            'country_id' : country_id[0],
            'email'      : email,
            'parent_id'  : billing_partner.id,
            'mobile'     : shipping_address['phone'],
            'phone'      : shipping_address['alternative_phone'],
            'name'       : shipping_address['full_name'],
        }

        shipping_partner = partner_db.create(cr, uid, vals)
        shipping_partner = partner_db.browse(cr, uid, shipping_partner)


        return billing_partner, shipping_partner






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







