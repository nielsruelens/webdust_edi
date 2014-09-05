from openerp.osv import osv
import grequests
import logging
import datetime
import json
from openerp.tools.translate import _


class spree_product_manager(osv.Model):
    _name = "product.product"
    _inherit = "product.product"

    def write(self, cr, uid, ids, vals, context=None):
        if not context: context = {}
        result = super(spree_product_manager, self).write(cr, uid,ids, vals, context)

        # Read customizing
        # ----------------
        log = logging.getLogger(None)
        settings = self.pool.get('clubit.tools.settings').get_settings(cr, uid)
        connection = [x for x in settings.connections if x.name == 'SPREE_PRODUCT_MANAGER' and x.is_active == True]
        if not connection:
            log.warning('SPREE_PRODUCT_PUSHER: Could not find the SPREE_PRODUCT_MANAGER connection settings, could not push product to Spree.')
            return result
        connection = connection[0]

        # Collect and push
        # lightweight pricing or full?
        # ----------------------------
        products_param = []
        if not context.get('only_prices', False):
            products_param = self.full_extract(cr, uid, ids, connection.partner, context)
        else:
            products_param = self.price_extract(cr, uid, ids, connection.partner, context)

        param = {'products': products_param, 'interface_name': 'handig'}
        url = '{!s}/{!s}'.format(connection.url,  'push_bulk')
        header = {'content-type': 'application/json', connection.user: connection.password}

        calls = [grequests.put(url, data=json.dumps(param), headers=header)]
        log.info(param)
        responses = grequests.map(calls, size=50)
        log.info(map(lambda x: x.text, responses))

        return result




    def full_extract(self, cr, uid, ids, partner, context):
        data = []

        product_hashes = self.read(cr, uid, ids, ['id', 'change_hash'], context=context)
        products = self.read(cr, uid, ids, ['id', 'name', 'categ_id', 'description', 'ean13', 'list_price', 'recommended_price', 'cost_price', 'sale_ok', 'change_hash', 'properties', 'images'], context=context)
        properties = self.pool.get('webdust.product.property').browse(cr, uid, [item for sublist in [x['properties'] for x in products] for item in sublist])
        images = self.pool.get('webdust.image').browse(cr, uid, [item for sublist in [x['images'] for x in products] for item in sublist])

        for product in products:

            # Only products whose hash has changed are pushed, unless explicitly asked
            # ------------------------------------------------------------------------
            if not context.get('save_anyway', False):
                if product['change_hash'] == [x['change_hash'] for x in product_hashes if x['id'] == product['id']][0]:
                    continue

            price = self.pool.get('product.pricelist').price_get(cr, uid, [partner.property_product_pricelist.id],
                                                                          product['id'],
                                                                          1.0,
                                                                          partner.id,
                                                                          { 'uom': 1, 'date': datetime.datetime.today().strftime('%Y-%m-%d'), })[partner.property_product_pricelist.id]
            param = {
                'id'          : str(product['id']),
                'name'        : product['name'],
                'description' : product['description'] or '',
                'sku'         : product['ean13'],
                'price'       : price or product['cost_price']*1.45,
                'cost_price'  : product['cost_price'],
                'recommended_retail_price' : product['recommended_price'],
                'shipping_category_id' : 1,
                'categ_id'    : product['categ_id'][0],
                'properties'  : [],
                'images'      : [],
            }

            param['images'] = [x.url for x in images if x.id in [y for y in product['images']]]
            param['properties'] = [{'name':x.name.name, 'value':x.value} for x in properties if x.id in [y for y in product['properties']] and x.name.visibility == 'external']

            if product['sale_ok']:
                param['available_on'] = datetime.datetime.today().strftime('%Y/%m/%d')
            else:
                param['available_on'] = '2999/12/31'

            data.append(param)

        return data


    def price_extract(self, cr, uid, ids, partner, context):
        data = []
        products = self.read(cr, uid, ids, ['id', 'cost_price'], context=context)
        for product in products:

            price = self.pool.get('product.pricelist').price_get(cr, uid, [partner.property_product_pricelist.id],
                                                                          product['id'],
                                                                          1.0,
                                                                          partner.id,
                                                                          { 'uom': 1, 'date': datetime.datetime.today().strftime('%Y-%m-%d'), })[partner.property_product_pricelist.id]
            param = {
                'id'    : str(product['id']),
                'price' : price or product['cost_price']*1.45,
            }
            data.append(param)
        return data


