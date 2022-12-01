window.addEventListener("load", () => {
  let last_data = null;
  const check_and_reload = () => {
    fetch(window.location.toString()).then((response) => response.text()).then((data) => {
      setTimeout(() => check_and_reload(), 200);
      if(last_data === null) {
        last_data = data;
        return;
      }
      if (last_data != data) {
        last_data = data;
        document.location.reload();
      }
    });
  };
  setTimeout(() => check_and_reload(), 200);
});
