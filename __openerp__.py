{
    'name': 'webdust_edi',
    'version': '1.0',
    'category': 'EDI',
    'description': "Custom EDI Implementation for Webdust",
    'author': 'Niels Ruelens',
    'website': 'http://clubit.be',
    'summary': 'Custom EDI Implementation for Webdust',
    'sequence': 9,
    'depends': [
        'edi',
        'clubit_tools',
        'purchase',
        'webdust_product',
        'clubit_mrp_auto_po_merge',
    ],
    'data': [
        'wizard/thr_masterdata_view.xml',
        'wizard/thr_product_combined_view.xml',
        'wizard/quotations_out_view.xml',
        'wizard/thr_ftp_download_view.xml',
        'purchase_view.xml',
        'sale_order_view.xml',
        'category_view.xml',
        'config.xml',
        'settings.xml',
        'schedulers.xml',
    ],
    'demo': [
    ],
    'test': [
    ],
    'css': [
    ],
    'images': [
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}