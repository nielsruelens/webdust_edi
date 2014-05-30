from openerp.osv import osv
from openerp.tools.translate import _
import ftplib
from os.path import join


# Helper function to read FTP directory
def list_files(ftp):
    ''' helper function to read an FTP directory '''
    files = []
    def dir_callback(line):
        bits = line.split()

        if ('d' not in bits[0]):
            files.append(bits)
    ftp.dir(dir_callback)
    return files


class product(osv.Model):

    _name = "product.product"
    _inherit = 'product.product'

    def thr_ftp_download(self, cr, uid):

        helpdesk_db = self.pool.get('crm.helpdesk')
        header = 'An error occurred during the THR_FTP download scheduler.'

        # Find the customizing
        # --------------------
        flow_db = self.pool.get('clubit.tools.edi.flow')
        flow_id = flow_db.search(cr, uid, [('model', '=', 'product.product'),('method', '=', 'edi_import_availability')])[0]
        settings = self.pool.get('clubit.tools.settings').get_settings(cr, uid)
        ftp_info = [x for x in settings.connections if x.name == 'THR_FTP']
        if not ftp_info:
            helpdesk_db.create_simple_case(cr, uid, header, 'Missing THR_FTP connection in the EDI settings')
            return True
        ftp_info = ftp_info[0]



        # Connect to the FTP server
        # -------------------------
        try:
            ftp = ftplib.FTP(ftp_info.url, ftp_info.user, ftp_info.password)
        except Exception as e:
            helpdesk_db.create_simple_case(cr, uid, header, 'Could not connect to FTP server at {!s}, error given: {!s}'.format(ftp_info.url, str(e)))
            return True


        # Move to the folder containing the files
        # ---------------------------------------
        success = ftp.cwd('Artikelgegevens')
        if not success:
            helpdesk_db.create_simple_case(cr, uid, header, 'Connected to FTP server {!s}, but could not find folder Artikelgegevens'.format(ftp_info.url))
            ftp.quit()
            return True


        # Download the 2 files we need
        # ----------------------------
        files = list_files(ftp)
        if not files:
            helpdesk_db.create_simple_case(cr, uid, header, 'Connected to FTP server {!s}, but folder Artikelgegevens did not contain any files'.format(ftp_info.url))
            ftp.quit()
            return True

        # We're looking for CSV files
        files = [f for f in files if f[-1][-3:] == 'csv']
        if not files:
            helpdesk_db.create_simple_case(cr, uid, header, 'Connected to FTP server {!s}, but folder Artikelgegevens did not contain any csv files'.format(ftp_info.url))
            ftp.quit()
            return True

        for f in files:
            # The masterdata file
            if f[-1][:11] == 'export_pim_':

                try:
                    path = join('EDI', cr.dbname, 'THR_product_upload', 'export_pim_handig.csv')
                    out = open(path, "wb")
                    ftp.retrbinary('RETR {!s}'.format(f[-1]), out.write)
                    out.close()
                except Exception as e:
                    helpdesk_db.create_simple_case(cr, uid, header, 'Tried to download file {!s} to {!s}, but got the following error: {!s}'.format(f[-1], path, str(e)))
                    return True



            elif f[-1][:10] == 'thr_stock_':

                try:
                    path = join('EDI', cr.dbname, str(ftp_info.partner.id), str(flow_id), f[-1])
                    out = open(path, "wb")
                    ftp.retrbinary('RETR {!s}'.format(f[-1]), out.write)
                    out.close()
                except Exception as e:
                    helpdesk_db.create_simple_case(cr, uid, header, 'Tried to download file {!s} to {!s}, but got the following error: {!s}'.format(f[-1], path, str(e)))
                    return True


        # Close the connection and leave the program
        # ------------------------------------------
        ftp.quit()
        exit()




