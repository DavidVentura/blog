I want to have internet usage data from my router as it cannot be put in bridge mode. I currently use the services of T-Mobile (NL).

## Investigating the data

These 'smart' people decided to do a POST that **never returns**. I guess that's to avoid people like me trying to get the data out of the browser easily with the dev tools.

![](images/router-home.png)

I inspected the button and saw it is calling `postData()`. The relevant part of the function is below:

`user_login.js`

```javascript
postData: function() {
    this.content.set("UserName", $("#index_username").val());
    this.content.set("Password", $("#password").val());
    if (check_username_password_if_blank()) {
        return 0
    }
    var a = utilGetCsrf();
    var c = {
        csrf: a,
        data: utilGetJson(this.content)
    };
    $("#password").blur();
    var b = this.content.get("UserName") + base64Encode(SHA256(this.content.get("Password"))) + a.csrf_param + a.csrf_token;
    c.data["Password"] = SHA256(b);
    this.post($.toJSON(c), function(d) {
        # ....
    }
}
``` 

`cat_exember.js.jgz`

```javascript
function utilGetCsrf() {
    if (g_csrf_obj){
        return g_csrf_obj;
    }
    var csrf_obj = {};
    var metas = document.getElementsByTagName("meta");
    var m;
    for(m = 0 ; m < metas.length; m++) {
      if (metas[m].getAttribute('name') === 'csrf_param') {
        csrf_obj.csrf_param = metas[m].getAttribute('content');
        break;
      }
    }
    for(m = 0 ; m < metas.length; m++){
      if (metas[m].getAttribute('name') === 'csrf_token') {
        csrf_obj.csrf_token = metas[m].getAttribute('content');
        break;
      }
    }
    return csrf_obj;
}
```

This router has some "security" measurements, all of the json outputs that this gives are surrounded by `while(1);/*` and `*/`.

## Rewriting

I rewrote this code in python

```python
def _hash(user, password, csrf_param, csrf_token):
    _pwd_hash = sha256(password.encode('utf-8')).hexdigest().encode('ascii')
    _b64 = base64.b64encode(_pwd_hash).decode('ascii')
    _b = user + _b64 + csrf_param + csrf_token
    _b = _b.encode('utf-8')
    return sha256(_b).hexdigest()

def find_csrf(html):
    csrf = {}
    soup = BeautifulSoup(html, 'html.parser')
    for meta in soup.find_all('meta'):
        if 'name' in meta.attrs and 'csrf' in meta.attrs['name']:
            key = meta.attrs['name']
            value = meta.attrs['content']
            csrf[key] = value
    return csrf
```


## Testing

I needed a way to test if my `_hash` function was correct, fortunately the router serves the web interface via plain http, so `mitmproxy` was enough to steal a few `csrf_token` and `csrf_param`, together with the final result.

## Flow

The actual flow of info to get the data out of the router is:

- GET / (for the original csrf\_token and csrf\_param and the cookie)
- POST /api/system/user\_login (with the csrf values, user and password (hashed), together with the cookie)
- GET /api/ntwk/wan\_st (with the csrf values, together with the cookie)
- Parse the "json" that's given by the router.
