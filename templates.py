## RepeatCellRequest to change the background color on a range of cells
def backgroundColor(col, start, end, sheetId, color):
     return({
        "repeatCell" : {
        "range" : {
            "sheetId" : sheetId,
            "startRowIndex" : start,
            "endRowIndex" : end,
            "startColumnIndex" : col,
            "endColumnIndex" : col + 1,
        },
        "cell" : {

                    "userEnteredFormat" : {
                        "backgroundColor" : {
                            "red" : color[0] / 255,
                            "green" : color[1] / 255, 
                            "blue" :  color[2] / 255
                        }
                    }
        },
        "fields" : "userEnteredFormat.backgroundColor"
        }
    })

## AutoResizeDimensionsRequest to automatically resize a column
def resizeColumn(col, sheetId):
    return({
        "autoResizeDimensions" : {
            "dimensions" : {
                "sheetId" : sheetId,
                "dimension" : "COLUMNS",
                "startIndex" : col,
                "endIndex" : col + 1
            }
        }
    })

## BatchUpdateRequest entry
def batchValueEntry(r, v):
    return({
        "range" : r,
        "values" : v
    })