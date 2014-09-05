from openerp.osv import osv
import grequests
import requests
import logging
import json
from openerp.tools.translate import _


class spree_shipment_manager(osv.Model):
    _name = "stock.picking"
    _inherit = "stock.picking"


    def do_partial(self, cr, uid, ids, partial_datas, context=None):
        """ Adds functionality to incoming shipment receive, send stock updates to spree
        @return: True
        """

        # Call the super method
        # ---------------------
        result = super(spree_shipment_manager, self).do_partial(cr, uid,ids, partial_datas, context)

        # Depending on wether or not this is an incoming our
        # outgoing delivery different actions need to be undertaken
        # ---------------------------------------------------------
        for picking in self.browse(cr, uid, ids):

            if picking.type == 'in':
                self.handle_incoming_shipment(cr, uid, picking, partial_datas)
            else:
                self.handle_outgoing_delivery(cr, uid, picking, partial_datas)

        return result




    def handle_incoming_shipment(self, cr, uid, picking, partial_datas):

        # Read customizing
        # ----------------
        log = logging.getLogger(None)
        settings = self.pool.get('clubit.tools.settings').get_settings(cr, uid)
        connection = [x for x in settings.connections if x.name == 'SPREE_PRODUCT_MANAGER' and x.is_active == True]
        if not connection:
            log.warning('SPREE_STOCK_MANAGER: Could not find the SPREE_PRODUCT_MANAGER connection settings, could not push shipment to Spree.')
            return False
        connection = connection[0]

        # Collect and push
        # ----------------
        lines = [x[1] for x in partial_datas.items() if x[0].find('move') != -1]

        calls = []
        for line in lines:
            url = '{!s}/{!s}/{!s}'.format(connection.url, str(line['product_id']), 'receive')
            header = {'content-type': 'application/json', connection.user: connection.password}
            param = { 'stock_movement' : { 'quantity': line['product_qty'] }, 'interface_name': 'handig'}
            calls.append(grequests.post(url, data=json.dumps(param), headers=header))
        grequests.map(calls, size=20)
        return True


    def handle_outgoing_delivery(self, cr, uid, picking, partial_datas):
        settings = self.pool.get('clubit.tools.settings').get_settings(cr, uid)
        connection = [x for x in settings.connections if x.name == 'SPREE_ORDER_MANAGER' and x.is_active == True]
        if not connection:
            return False
        order_connection = connection[0]

        connection = [x for x in settings.connections if x.name == 'SPREE_SHIPMENT_MANAGER' and x.is_active == True]
        if not connection:
            return False
        shipment_connection = connection[0]

        if not picking.sale_id.client_order_ref:
            return False

        url = '{!s}/{!s}'.format(order_connection.url, picking.sale_id.client_order_ref)
        header = {'content-type': 'application/json', order_connection.user: order_connection.password}

        try:
            r = requests.get(url, headers=header)
        except Exception as e:
            return False
        if r.status_code != 200:
            return False
        response = json.loads(r.text)

        calls = []
        for shipment in response['shipments']:
            if shipment['state'] != 'ready':
                continue
            header = {'content-type': 'application/json', shipment_connection.user: shipment_connection.password}
            url = '{!s}/{!s}/ship'.format(shipment_connection.url, shipment['number'])
            calls.append(grequests.put(url, headers=header))
        if calls:
            grequests.map(calls, size=50)
        return True








