import json

def ndjsondumps(jsonobj):
    """takes a list of repeated json objects and returns a newline delimited json string"""
    jsonstrs = []
    for obj in jsonobj:
        jsonstrs.append(json.dumps(obj))
    return '\n'.join(jsonstrs)
