##Generates 10-20.png using the 0-9.png assets extracted from the wz files

from PIL import Image

def merge(f1, f2):

	##open both images
	img1 = Image.open(f1)
	img2 = Image.open(f2)
	
	##save sizes
	(w1, h1) = img1.size
	(w2, h2) = img2.size
	
	##set result w + h
	rw = w1 + w2
	rh = max(h1, h2)
	
	##create merged image
	res = Image.new('RGBA', (rw, rh))
	res.paste(im=img1, box=(0,0))
	res.paste(im=img2, box=(w1, 0))
	return(res)
	
	
for i in range(10, 21):
	##cast as string for indexing
	d = str(i)
	##merge and saver
	merge("{0}.png".format(d[0]), "{0}.png".format(d[1])).save("{0}.png".format(i))