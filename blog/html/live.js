async function fresherThan(url, date) {
    const response = await fetch(url, {method: 'HEAD', headers: {'If-Modified-Since': date.toGMTString()}});
    return response.status !== 304;
}

window.addEventListener("load", () => {
    let now = new Date();
    const check_and_reload = (when) => {
        if (when !== undefined) {
            now = when;
        }

        fetch(window.location.toString(), {method: 'HEAD', headers: {'If-Modified-Since': now.toGMTString()}}).then((response) => {

            if(response.status === 304) {
                setTimeout(() => check_and_reload(), 100);
                return;
            }

            fetch(window.location.toString())
                .then(response => response.text())
                .then(text => {
                    const parser = new DOMParser();
                    const newDoc = parser.parseFromString(text, 'text/html');
                    const position = document.scrollingElement.scrollTop;
                    document.body.replaceWith(newDoc.body);
                    /*
                    [...document.body.querySelectorAll('img')].forEach(img => {
                        img.src = `${img.src}?whatever=${now.toISOString()}`
                    });
                    setTimeout(() => {document.scrollingElement.scrollTop = position}, 50);
                    causes FOUC SAD
                    */
                    
                    setTimeout(() => check_and_reload(new Date()), 300);
                });
        });
    };
    setTimeout(() => check_and_reload(), 200);
});
