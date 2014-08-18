from openerp.osv import osv
import grequests
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

        # Read customizing
        # ----------------
        log = logging.getLogger(None)
        settings = self.pool.get('clubit.tools.settings').get_settings(cr, uid)
        connection = [x for x in settings.connections if x.name == 'SPREE_SHIPMENT_MANAGER' and x.is_active == True]
        if not connection:
            log.warning('SPREE_SHIPMENT_MANAGER: Could not find the SPREE_SHIPMENT_MANAGER connection settings, could not push shipment to Spree.')
            return result
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
        return result






