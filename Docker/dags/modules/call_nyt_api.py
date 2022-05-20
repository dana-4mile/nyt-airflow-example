import requests

def call_nyt_api(endpoint, api_key, api_args):
    """A function to call any NYT api endpoint.
    api_args is a dict of parameters that are appended to the API request string
    returns a json object. pass a null dict if you have no additional args."""
    args = []
    for arg in api_args.items():
        full_arg = "&{key}={value}".format(key=arg[0],value=arg[1])
        args.append(full_arg)
    arg_string = ''.join(args)
    request_string = ("{endpoint}?api-key={api_key}{arg_string}".format(endpoint=endpoint, api_key=api_key, arg_string=arg_string))
    api_obj = requests.get(request_string)
    print(f"API HTTP Response: {api_obj.status_code}")
    return api_obj.json()
