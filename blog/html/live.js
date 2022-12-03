window.addEventListener("load", () => {
  const now = new Date();
  const check_and_reload = () => {
    fetch(window.location.toString(), {method: 'HEAD', headers: {'If-Modified-Since': now.toGMTString()}}).then((response) => {
      setTimeout(() => check_and_reload(), 200);
      if(response.status === 304) {
        return;
      }
      document.location.reload();
    });
  };
  setTimeout(() => check_and_reload(), 200);
});
