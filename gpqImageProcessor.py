import cv2 as cv
import numpy as np
import pytesseract as tess
from google.oauth2 import service_account
from google.cloud import vision
import numpy
import config
import traceback

from tabulate import tabulate

import pickle

from time import perf_counter
from contextlib import contextmanager

@contextmanager
def catchtime(label = "") -> float:
    start = perf_counter()
    yield lambda: perf_counter() - start
    print(f'{label} Time: {perf_counter() - start:.3f} seconds')

class GPQImageProcessor():
    
    def __init__(self):
        self.tessConfig = ("--oem 1")

        self.keyfile = config.VISION_CRED_FILE
        if(self.keyfile):
            self.creds = service_account.Credentials.from_service_account_file(filename=self.keyfile, scopes=["https://www.googleapis.com/auth/cloud-platform"])
            self.client = vision.ImageAnnotatorClient(credentials=self.creds)
        else:
            self.client = None
        


    def readScores(self, im, fit, precropped=False):

        scale = fit[2]

        SCALE_FACTOR = 2

        # If the locating worked, these are the hard coords of the information we want
        # We do need to scale it by the factor we determined the input was scaled by.
        X, Y = (int(20 * scale), int(87 * scale))
        X2, Y2 = (int(503 * scale), int(502 * scale))
        
        if not precropped:
            im = im[Y:Y2, X:X2]
        else:
            ## Crop down to 483 x 415 (scale 1)
            deltaX = max(int((im.shape[1] - (483 * scale)) / 2), 0)
            deltaY = max(int((im.shape[0] - (415 * scale)) / 2), 0)
            im = im[deltaY:im.shape[1] - deltaY, deltaX:im.shape[1] - deltaX]
             

        #Resize and grayscale
        im2 = cv.resize(im, (im.shape[1] * SCALE_FACTOR, im.shape[0] * SCALE_FACTOR), interpolation = cv.INTER_CUBIC)
        gray = cv.cvtColor(im, cv.COLOR_BGR2GRAY)

        # clean image
        ret, thresh = cv.threshold(gray, 125, 255, cv.THRESH_BINARY)
        thresh = cv.resize(thresh, (thresh.shape[1] * SCALE_FACTOR, thresh.shape[0] * SCALE_FACTOR), interpolation = cv.INTER_CUBIC)

        cv.imwrite("thresh.png", thresh)

        # blur horizontally for contour detection
        kernel = cv.getStructuringElement(cv.MORPH_RECT, (int(460 * SCALE_FACTOR/2), int(14 * SCALE_FACTOR/2)))
        morph = cv.morphologyEx(thresh, cv.MORPH_DILATE, kernel)

        cv.imwrite("morph.png", morph)

        # find contours
        contours = cv.findContours(morph, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        contours = contours[0] if len(contours) == 2 else contours[1]

        # Invert colors (I think tess likes black on white better?)
        thresh = cv.bitwise_not(thresh)

        # Magic
        kernel = np.ones((5, 5), np.float32)/30
        magicThresh = cv.filter2D(thresh, -1, kernel)

        # Iterate over contours (effectively parsing each line individually)
        res = []
        for c in contours:

            # Grab the bounding box for each contour
            box = cv.boundingRect(c)
            x, y, w, h = box
            cv.rectangle(im2, (x, y), (x+w, y+h), (0, 0, 255), 1)

            # Crop and OCR just the current line
            crop = thresh[y:y+h, x:x+w]
            magicCrop = magicThresh[y:y+h, x:x+w]
            
            out = tess.image_to_string(magicCrop,config=self.tessConfig)
            nameOut = tess.image_to_string(crop,config=self.tessConfig)
            
            # Clean data
            out = out.replace("\n", " ").strip()
            out = out.replace("Oo", " 0 0 ")
            nameOut = nameOut.replace("\n", " ").strip()
            nameOut = nameOut.replace("Oo", " 0 0 ")

            s = [x for x in out.split(" ") if not x == ""]
            s2 = [x for x in nameOut.split(" ") if not x == ""]


            # Convert trailing entries to integers until we find one that cant be converted
            i = 0
            for i in range(len(s) - 1, 0, -1):
                if(not isInt(s[i])):
                    break
                else:
                    s[i] = int(s[i].replace(",", ""))
            
            if len(s) == 0:
                continue
            elif len(s) == 1:
                s.insert(0, "")
            
            ## s2 should have have better name reading
            if(len(s2) >= 1 and len(s) > 1):
                ## a period in the name indicates it was shortened, filter out what comes after
                ## TODO: additional flag possibly, change future matching to only match up to the length of name
                ## EX: ign "Lostara", matched "Lost..", shorten look up to 4 characters, so we are only matching the part we have  
                name = s2[0]
                if "." in name:
                    name = name[:name.index(".")]
                s[0] = name

            s = [x for x in s if not (type(x) == int and x < 10)]

            while not (type(s[-1]) == int and type(s[-2]) == int):
                s.append(0)

            res.append(s)
        
        return(res, im2)


    def matchGuildUI(self, img):
        template = cv.imread("assets/member_participation_status.png")
        baseH, baseW = template.shape[:2]

        edges = cv.Canny(img.copy(), 150, 200)

        bestFit = None
        bestCrop = None

        for scale in np.linspace(0.5, 2.0, 7):
            # resize template to a scale
            templateR = cv.resize(template.copy(), (int(baseW * scale), int(baseH * scale)), cv.INTER_CUBIC)
            templateR = cv.Canny(templateR.copy(), 150, 200)
            tH, tW = templateR.shape[:2]
            
            # make sure our template isn't larger than the matcher
            if(img.shape[1] <= tW or img.shape[0] <= tH):
                continue
            
            # Find best match
            matches = cv.matchTemplate(edges, templateR, cv.TM_CCOEFF)
            minVal, maxVal, minLoc, maxLoc = cv.minMaxLoc(matches)

            #If this is our best overall match, save it
            if(bestFit == None or bestFit[0] < maxVal):
                bestFit = (maxVal, maxLoc, scale)
                bestCrop = img.copy()[maxLoc[1]:maxLoc[1]+tH, maxLoc[0]:maxLoc[0]+tW]

        cv.imwrite("crop.png", bestCrop)
        return(bestCrop, bestFit)


    def readScoresGoogle(self, image, fit, precropped=False):

        ret, thresh = cv.threshold(image, 100, 255, cv.THRESH_BINARY)
        
        scale = fit[2]
        X, Y = (int(20 * scale), int(40 * scale))
        X2, Y2 = (int(503 * scale), int(502 * scale))

        if not precropped:
            im = thresh[Y:Y2, X:X2]
        else:
            deltaX = max(int((thresh.shape[1] - (483 * scale)) / 2), 0)
            deltaY = max(int((thresh.shape[0] - (415 * scale)) / 2), 0)
            im = thresh[deltaY:thresh.shape[1] - deltaY, deltaX:thresh.shape[1] - deltaX - 20]

        im = cv.cvtColor(im, cv.COLOR_BGR2GRAY)

        kernel = cv.getStructuringElement(cv.MORPH_RECT, (int(460), int(7)))
        morph = cv.morphologyEx(im, cv.MORPH_DILATE, kernel)

        # find contours
        contours = cv.findContours(morph, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        contours = contours[0] if len(contours) == 2 else contours[1]

        imH, imW = im.shape

        newImg = numpy.zeros((int(40 * scale) * len(contours), imW))
        print(newImg.shape)

        for i, c in enumerate(reversed(contours)):

            # Grab the bounding box for each contour
            box = cv.boundingRect(c)
            x, y, w, h = box
            newImg[i*int(40*scale):i*int(40*scale)+h, x:x+w] = im[y:y+h, x:x+w]
            cv.rectangle(im, (x, y - 2), (x+w, y+h + 2), (255, 255, 255), 1)
            
        cv.imwrite("cropped.png", im) 
        cv.imwrite("copped2.png", newImg)

        success, encodedImage = cv.imencode(".png", newImg)
        imageBytes = encodedImage.tobytes()

        visionImage = vision.Image(content=imageBytes)
        response = self.client.text_detection(image=visionImage)

        if response.error.message:
            print(response.error.message)
            return False, None
        else:
            with open("resp4.pickle", "wb") as f:
                pickle.dump(response, f)
            annotations = response.text_annotations
            outDict = {}
            for a in annotations[1:]:
                vertices = a.bounding_poly.vertices
                vert1 = vertices[0]

                ##TODO: append whole annotation for 0->x sorting
                outDict.setdefault(vert1.y // int(40*scale), []).append(a.description.replace(",", ""))

            keys = sorted(list(outDict.keys()))

            outArr = [outDict[k] for k in keys]

            return(outArr, newImg)


    def processImage(self, image, full=True):
        
        originalImage = image.copy()
        fit = [0, image.shape, 1]

        if full:
            with catchtime("Match Guild UI") as t:
                image, fit = self.matchGuildUI(image)
                #cv.imwrite("matchedUI.png", image)

        results = None
        debugImage = None

        if self.client:
            try:
                with catchtime("Read Scores Google") as t:
                    results, debugImage = self.readScoresGoogle(image, fit, precropped = not full)
                    results = [x for x in results if not x[0] in ["Name", "Change"]]
                    print(results)
                    with open("newMethod.txt", "a") as f:
                        f.write(tabulate([[x[0], x[-2]] for x in results], headers=["IGN", "Score"]))
            except Exception as e:
                print("Exception in Read Scores Google: {0}".format(self.client))
                print(traceback.print_exc())

        ## Handles no client or exception in read scores google
        if results == None:
            with catchtime("Read Scores Tess") as t:
                results, debugImage = self.readScores(image, fit, precropped = not full)
                results.reverse()
                with open("oldMethod.txt", "a") as f:
                    f.write(tabulate([[x[0], x[-2]] for x in results], headers=["IGN", "Score"]))

            
        return(results, debugImage, fit)

def isInt(i):
    try:
        i = i.replace(",", "")
        i = int(i)
        return(True)
    except:
        return(False)


def main():
    processor = GPQImageProcessor()
    image = cv.imread("pA7kCRQ.png")
    #cv.imshow("test", image)
    #cv.waitKey(0)
    processor.processImage(image, full=False)


if __name__ == "__main__":
    main()