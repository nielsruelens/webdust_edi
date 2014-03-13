from openerp.osv import osv,fields
from openerp.tools.translate import _



class product_category(osv.Model):
    _name = "product.category"
    _inherit = "product.category"


    def edi_partner_resolver(self, cr, uid, ids, context):
        ''' product.category:edi_partner_resolver()
            ---------------------------------------
            This method attempts to find the correct partner
            to whom we should send an EDI document for a
            number of categories. Since this interface
            always communicates to "Spree", the partner is
            always "Spree".
            ------------------------------------------------ '''

        result_list = []
        partner_db = self.pool.get('res.partner')
        partner_ids = partner_db.search(cr, uid, [('name', '=', 'Spree')])

        for category in ids:
            result_list.append({'id' : category, 'partner_id': partner_ids[0]})
        return result_list



    def send_edi_out(self, cr, uid, items, context=None):
        ''' product.category:send_edi_out()
            -------------------------------
            This method will perform the export of a product
            category, the simple version.
            ------------------------------------------------ '''


        edi_db = self.pool.get('clubit.tools.edi.document.outgoing')

        # Get the selected items
        # ----------------------
        cat_ids = [x['id'] for x in items]
        categories = self.browse(cr, uid, cat_ids, context=context)


        # Actual processing of all the categories
        # ---------------------------------------
        content = []
        for category in categories:
            content.append({ 'id' : category.id, 'name' : category.name, 'code': category.code, 'parent_id':category.parent_id.id})

        result = edi_db.create_from_content(cr, uid, 'categories_to_spree', content, items[0]['partner_id'], 'product.category', 'send_edi_out')
        if result != True:
            raise osv.except_osv(_('Error!'), _("Something went wrong while trying to create one of the EDI documents. Please contact your system administrator. Error given: {!s}").format(result))








class product_product(osv.Model):
    _name = "product.product"
    _inherit = "product.product"


    def edi_partner_resolver(self, cr, uid, ids, context):
        ''' product.product:edi_partner_resolver()
            --------------------------------------
            This method attempts to find the correct partner
            to whom we should send an EDI document for a
            number of categories. Since this interface
            always communicates to "Spree", the partner is
            always "Spree".
            ------------------------------------------------ '''

        result_list = []
        partner_db = self.pool.get('res.partner')
        partner_ids = partner_db.search(cr, uid, [('name', '=', 'Spree')])

        for category in ids:
            result_list.append({'id' : category, 'partner_id': partner_ids[0]})
        return result_list



    def send_edi_out(self, cr, uid, items, context=None):
        ''' product.product:send_edi_out()
            ------------------------------
            This method will perform the export of a product.
            ------------------------------------------------- '''


        edi_db = self.pool.get('clubit.tools.edi.document.outgoing')

        # Get the selected items
        # ----------------------
        prod_ids = [x['id'] for x in items]
        products = self.browse(cr, uid, prod_ids, context=context)


        # Actual processing of all the products
        # -------------------------------------
        content = []
        for product in products:
            vals = { 'id': product.id, 'name':product.name, 'ean': product.ean13,
                     'category': product.categ_id.code, 'properties':[], 'images':[],
                     'recommended_price':product.recommended_price,
                     'long_description':product.description_sale, 'short_description':product.short_description}
            for property in product.properties:
                vals['properties'].append({'id':property.name.id, 'name':property.name.name, 'value':property.value})
            for image in product.images:
                vals['images'].append({'supplier':image.supplier.id, 'url':image.url})
            content.append(vals)


        result = edi_db.create_from_content(cr, uid, 'products_to_spree', content, items[0]['partner_id'], 'product.product', 'send_edi_out')
        if result != True:
            raise osv.except_osv(_('Error!'), _("Something went wrong while trying to create one of the EDI documents. Please contact your system administrator. Error given: {!s}").format(result))





    def send_edi_out_pricing(self, cr, uid, items, context=None):
        ''' product.product:send_edi_out_pricing()
            --------------------------------------
            This method will perform the export of
            pricing and availability information to Spree.
            ---------------------------------------------- '''


        edi_db = self.pool.get('clubit.tools.edi.document.outgoing')
        comp_db = self.pool.get('res.company')
        partner_db = self.pool.get('res.partner')
        plist_db = self.pool.get('product.pricelist')
        company = False

        if 'company' not in context:
            (comp_id,) = comp_db.search(cr, uid, [])
            company = comp_db.browse(cr, uid, comp_id, context=context)
        else:
            company = comp_db.browse(cr, uid, context['company'], context=context)

        # Get the selected items
        # ----------------------
        prod_ids = [x['id'] for x in items]
        products = self.browse(cr, uid, prod_ids, context=context)


        # Actual processing of all the products
        # -------------------------------------
        content = []
        for product in products:

            price = plist_db.price_get(cr,uid,[company.partner_id.property_product_pricelist.id], product.id, 1, None)[company.partner_id.property_product_pricelist.id]
            if not price:
                price = product.list_price

            obsolete = False
            if product.state == 'obsolete':
                obsolete = True
            vals = { 'id': product.id, 'ean': product.ean13, 'code': product.default_code, 'sale_price': price,
                     'cost_price': product.cost_price, 'recommended_price': product.recommended_price,
                     'can_be_sold': product.sale_ok, 'obsolete': obsolete}
            content.append(vals)


        result = edi_db.create_from_content(cr, uid, 'pricing_to_spree', content, items[0]['partner_id'], 'product.product', 'send_edi_out_pricing')
        if result != True:
            raise osv.except_osv(_('Error!'), _("Something went wrong while trying to create one of the EDI documents. Please contact your system administrator. Error given: {!s}").format(result))























