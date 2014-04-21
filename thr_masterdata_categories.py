from openerp.osv import osv, fields
from openerp.tools.translate import _
import logging
import threading
from openerp import pooler


class product_category(osv.Model):

    _name = "product.category"
    _inherit = 'product.category'
    _description = "Category extensions"

    _columns = {
        'code' : fields.char('Code', size=64, required=False),
    }

    log = logging.getLogger(None)


    def upload_thr(self, cr, uid, categories, context=None):
        """
        This method takes in the categories as defined by THR and
        makes sure they exist in OpenERP.
        For performance reasons, this method keeps track of
        everything that has already been processed, since the
        file contains a lot of duplicates and this REALLY drains
        performance.
        """

        self.log.info('UPLOAD_THR-CATEGORIES: starting on the categories.')
        self.log.info('UPLOAD_THR-CATEGORIES: removing duplicate entries from input.')
        categories = set(tuple(element) for element in categories)
        processed = {}


        for i in range(5):

            level = i+1
            level_start = level * 2 - 2
            self.log.info('UPLOAD_THR-CATEGORIES: starting on the categories: level {!s}.'.format(level))
            cats = [ x[level_start:level_start+2] for x in categories ] #extract category details (code + description)
            cats = list(set(tuple(element) for element in cats))        #remove duplicates from the filtered list -> convert the set back to a list so we can slice

            #level 1 0:2
            #level 2 2:4
            #level 3 4:6
            #level 4 6:8
            #level 5 8:10

            parent = 0
            my_loc = 0
            if level != 1:
                my_loc = level * 2 - 2
                parent = my_loc - 2


            # Get the ids + content for all the codes that already exist
            self.log.info('UPLOAD_THR-CATEGORIES: read pre-existing categories.')
            cat_ids = self.search(cr, uid, [('code', 'in', [ x[0] for x in cats ])])
            all_existing = self.browse(cr, uid, cat_ids, context=context)

            for i, cat in enumerate(cats):
                i = i + 1
                self.log.info('UPLOAD_THR-CATEGORIES: processing category {!s} ({!s} of {!s}) '.format(cat[0], i, len(cats)))
                # Check if the element already exists
                existing = next((x for x in all_existing if x.code == cat[0]), None)
                if existing:
                    processed[cat[0]] = existing.id
                    if existing.name != cat[1]:
                        self.write(cr, uid, existing.id, {'name': cat[1]}, context)
                else:
                    # Doesn't exist, create the item
                    vals = {}
                    (vals['code'], vals['name']) = cat

                    # there's a parent node
                    if level > 1:
                        code = next(x[parent] for x in categories if x[my_loc] == cat[0])
                        vals['parent_id'] = processed[code]


                    processed[cat[0]] = self.create(cr, uid, vals, context)

            cr.commit()
            self.log.info('UPLOAD_THR-CATEGORIES: category level {!s} upload complete.'.format(level))








