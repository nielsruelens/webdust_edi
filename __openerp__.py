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
    ],
    'data': [
        'wizard/product_upload_thr_view.xml',
        'wizard/category_download_spree_view.xml',
        'wizard/product_download_spree_view.xml',
        'wizard/pricing_download_spree_view.xml',
        'purchase_view.xml',
        'category_view.xml',
        'config.xml',
        'settings.xml',
        'wizard/clubit_tools_edi_wizard_outgoing_purchase.xml',
        'wizard/clubit_tools_edi_wizard_outgoing_category.xml',
        'wizard/clubit_tools_edi_wizard_outgoing_product.xml',
        'wizard/clubit_tools_edi_wizard_outgoing_pricing.xml',
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