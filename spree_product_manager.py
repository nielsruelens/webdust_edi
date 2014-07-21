from openerp.osv import osv
import grequests
import logging
import datetime
import json
from openerp.tools.translate import _


class product_product(osv.Model):
    _name = "product.product"
    _inherit = "product.product"

    def write(self, cr, uid, ids, vals, context=None):
        result = super(product_product, self).write(cr, uid,ids, vals, context)

        # Read customizing
        # ----------------
        log = logging.getLogger(None)
        settings = self.pool.get('clubit.tools.settings').get_settings(cr, uid)
        connection = [x for x in settings.connections if x.name == 'SPREE_PRODUCT_MANAGER']
        if not connection:
            log.warning('SPREE_PRODUCT_PUSHER: Could not find the SPREE_PRODUCT_MANAGER connection settings, could not push product to Spree.')
            return result
        connection = connection[0]

        # Collect and push
        # ----------------
        products = self.read(cr, uid, ids, ['id', 'name', 'description', 'ean13', 'list_price', 'standard_price', 'sale_ok'], context=context)

        calls = []
        for product in products:
            url = '{!s}/{!s}/{!s}'.format(connection.url, str(product['id']), 'push')
            header = {'content-type': 'application/json', connection.user: connection.password}
            param = { 'product' : {
                'name'        : product['name'],
                'description' : product['description'],
                'sku'         : product['ean13'],
                'price'       : product['list_price'],
                'cost_price'  : product['cost_price'],
                'shipping_category_id' : 1,
            }, 'interface_name': 'handig'}
            if product['sale_ok']:
                param['product']['available_on'] = datetime.datetime.today().strftime('%Y/%m/%d')
            else:
                param['product']['available_on'] = '2999/12/31'

            calls.append(grequests.put(url, data=json.dumps(param), headers=header))
        grequests.map(calls, size=20)
        return result






