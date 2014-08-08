from openerp.osv import osv
import ftplib
import logging
import datetime
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


class webdust_thr_ftp_download(osv.TransientModel):
    _name = 'webdust.thr.ftp.download'
    _description = 'Class to immediately download everything from the THR FTP.'

    def start(self, cr, uid, ids, context=None):
        self.thr_ftp_download(cr, uid)
        return {'type': 'ir.actions.act_window_close'}




    def thr_ftp_download(self, cr, uid):

        log = logging.getLogger(None)
        log.info('THR_FTP: Starting the THR_FTP download process.')

        helpdesk_db = self.pool.get('crm.helpdesk')
        header = 'An error occurred during the THR_FTP download scheduler.'

        # Find the customizing
        # --------------------
        log.info('THR_FTP: Searching for the THR_FTP connection settings.')
        flow_db = self.pool.get('clubit.tools.edi.flow')
        flow_id = flow_db.search(cr, uid, [('model', '=', 'product.product'),('method', '=', 'edi_import_availability')])[0]
        settings = self.pool.get('clubit.tools.settings').get_settings(cr, uid)
        ftp_info = [x for x in settings.connections if x.name == 'THR_FTP' and x.is_active == True]
        if not ftp_info:
            log.warning('THR_FTP: Could not find the THR_FTP connection settings, creating CRM helpdesk case.')
            helpdesk_db.create_simple_case(cr, uid, header, 'Missing THR_FTP connection in the EDI settings')
            return True
        ftp_info = ftp_info[0]



        # Connect to the FTP server
        # -------------------------
        try:
            log.info('THR_FTP: Connecting to the FTP server.')
            ftp = ftplib.FTP(ftp_info.url, ftp_info.user, ftp_info.password)
        except Exception as e:
            log.warning('THR_FTP: Could not connect to FTP server at {!s}, error given: {!s}'.format(ftp_info.url, str(e)))
            helpdesk_db.create_simple_case(cr, uid, header, 'Could not connect to FTP server at {!s}, error given: {!s}'.format(ftp_info.url, str(e)))
            return True


        # Move to the folder containing the files
        # ---------------------------------------
        success = ftp.cwd('Artikelgegevens')
        if not success:
            log.warning('THR_FTP: Connected to FTP server {!s}, but could not find folder Artikelgegevens'.format(ftp_info.url))
            helpdesk_db.create_simple_case(cr, uid, header, 'Connected to FTP server {!s}, but could not find folder Artikelgegevens'.format(ftp_info.url))
            ftp.quit()
            return True


        # Download the 2 files we need
        # ----------------------------
        log.info('THR_FTP: Searching for files.')
        files = list_files(ftp)
        if not files:
            log.warning('THR_FTP: Connected to FTP server {!s}, but folder Artikelgegevens did not contain any files'.format(ftp_info.url))
            helpdesk_db.create_simple_case(cr, uid, header, 'Connected to FTP server {!s}, but folder Artikelgegevens did not contain any files'.format(ftp_info.url))
            ftp.quit()
            return True

        # Look for the latest delta file
        # ------------------------------
        now = datetime.datetime.now()
        delta = [(x[-1],datetime.datetime.strptime('-'.join([str(now.year),x[5],str(x[6])]), '%Y-%b-%d')) for x in files if x[-1].find('delta') != -1]
        if not delta:
            log.warning('THR_FTP: Connected to FTP server {!s}, but folder Artikelgegevens did not contain any delta files'.format(ftp_info.url))
            helpdesk_db.create_simple_case(cr, uid, header, 'Connected to FTP server {!s}, but folder Artikelgegevens did not contain any delta files'.format(ftp_info.url))
            ftp.quit()
            return True

        youngest_delta = max(x for x in delta if x[1] < now)
        log.info('THR_FTP: downloading delta masterdata file...')
        try:
            path = join('EDI', cr.dbname, 'THR_product_upload', youngest_delta[0])
            out = open(path, "wb")
            ftp.retrbinary('RETR {!s}'.format(youngest_delta[0]), out.write)
            out.close()
        except Exception as e:
            log.warning('THR_FTP: Tried to download file {!s} to {!s}, but got the following error: {!s}'.format(youngest_delta[0], path, str(e)))
            helpdesk_db.create_simple_case(cr, uid, header, 'Tried to download file {!s} to {!s}, but got the following error: {!s}'.format(youngest_delta[0], path, str(e)))
            ftp.quit()
            return True

        # Look for the latest stock file
        # ------------------------------
        stock = [x for x in files if x[-1].find('thr_stock_') != -1 and x[-1][-3:] == 'csv']
        if stock:
            log.info('THR_FTP: downloading stock file...')
            stock = stock[0]
            try:
                path = join('EDI', cr.dbname, str(ftp_info.partner.id), str(flow_id), '-'.join([stock[5], stock[6], stock[7],stock[-1]]))
                out = open(path, "wb")
                ftp.retrbinary('RETR {!s}'.format(stock[-1]), out.write)
                out.close()
            except Exception as e:
                log.warning('THR_FTP: Tried to download file {!s} to {!s}, but got the following error: {!s}'.format(stock, path, str(e)))
                helpdesk_db.create_simple_case(cr, uid, header, 'Tried to download file {!s} to {!s}, but got the following error: {!s}'.format(stock, path, str(e)))
                ftp.quit()
                return True


        # Close the connection and leave the program
        # ------------------------------------------
        ftp.quit()
        log.info('THR_FTP: Process is complete.')
        return True

