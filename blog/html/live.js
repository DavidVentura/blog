window.addEventListener("load", () => {
    let now = new Date();
    const check_and_reload = (when) => {
        if (when !== undefined) {
            now = when;
        }

        fetch(window.location.toString(), {method: 'HEAD', headers: {'If-Modified-Since': now.toGMTString()}}).then((response) => {
            if(response.status === 304) {
                setTimeout(() => check_and_reload(), 200);
                return;
            }
            fetch(window.location.toString())
                .then(response => response.text())
                .then(text => {
                    const parser = new DOMParser();
                    const newDoc = parser.parseFromString(text, 'text/html');
                    document.body.replaceWith(newDoc.body);
                    console.log('replaced');
                    setTimeout(() => check_and_reload(new Date()), 200);
                });
        });
    };
    setTimeout(() => check_and_reload(), 200);
});
