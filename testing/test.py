import erppeek
import csv
import cProfile

server = erppeek.Client('http://localhost:8069', 'handigDev', 'admin', 'clubit.bvba')

content = []
with open('export_pim_handig.csv', 'rb') as csvfile:
    reader = csv.reader(csvfile, delimiter=',', quotechar='"')
    for row in reader:
        content.append(row)


# Process the categories, exclude the header
# ------------------------------------------
cat_db = server.model('product.category')
toestanden = [ x[2:12] for x in content[1:] ]
cProfile.run(server.execute('product.category', 'upload_thr', toestanden))