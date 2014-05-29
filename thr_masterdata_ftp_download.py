from openerp.osv import osv
from openerp.tools.translate import _
import ftplib, config


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

        # Connect to the FTP server
        # -------------------------
        try:
            ftp = ftplib.FTP(config.ftp['address'], config.ftp['user'], config.ftp['password'])
        except Exception as e:
            self.create_helpdesk_case(cr, uid, 'Could not connect to FTP server at {!s}, error given: {!s}'.format(config.ftp['address'], str(e)))
            return True


        # Move to the folder containing the files
        # ---------------------------------------
        success = ftp.cwd(config.ftp['directory'])
        if not success:
            self.create_helpdesk_case(cr, uid, 'Connected to FTP server {!s}, but could not find folder {!s}'.format(config.ftp['address'], config.ftp['directory']))
            ftp.quit()
            return True


        # Download the 2 files we need
        # ----------------------------
        files = list_files(ftp)
        if not files:
            self.create_helpdesk_case(cr, uid, 'Connected to FTP server {!s}, but folder {!s} did not contain any files'.format(config.ftp['address'], config.ftp['directory']))
            ftp.quit()
            return True

        # We're looking for CSV files
        files = [f for f in files if f[-1][-3:] == 'csv']
        if not files:
            self.create_helpdesk_case(cr, uid, 'Connected to FTP server {!s}, but folder {!s} did not contain any csv files'.format(config.ftp['address'], config.ftp['directory']))
            ftp.quit()
            return True

        for f in files:
            # The masterdata file
            if f[-1][:11] == 'export_pim_':

                try:
                    out = open(config.targets['masterdata'], "wb")
                    ftp.retrbinary('RETR {!s}'.format(f[-1]), out.write)
                    out.close()
                except Exception as e:
                    self.create_helpdesk_case(cr, uid, 'Tried to download file {!s} to {!s}, but got the following error: {!s}'.format(f[-1], config.targets['masterdata'], str(e)))
                    return True



            elif f[-1][:10] == 'thr_stock_':

                try:
                    out = open(''.join([config.targets['stock'], f[-1]]), "wb")
                    ftp.retrbinary('RETR {!s}'.format(f[-1]), out.write)
                    out.close()
                except Exception as e:
                    self.create_helpdesk_case(cr, uid, 'Tried to download file {!s} to {!s}, but got the following error: {!s}'.format(f[-1],
                                                                                                    ''.join([config.targets['stock'], f[-1]]), str(e)))
                    return True


        # Close the connection and leave the program
        # ------------------------------------------
        ftp.quit()
        exit()




    def create_helpdesk_case(self, cr, uid, content):
        helpdesk_db = self.pool.get('crm.helpdesk')
        helpdesk_db.create(cr, uid, {'user_id': 6, 'name': content })




