// Adapted from https://gist.github.com/ciotlosm/1f09b330aa5bd5ea87b59f33609cc931
if (window.location.href.indexOf('kiosk') > 0) {
    setTimeout(function () {
        try {
            const home_assistant_main =  document
                  .querySelector("body > home-assistant").shadowRoot
                  .querySelector("home-assistant-main");

            var header = home_assistant_main.shadowRoot
                  .querySelector("app-drawer-layout > partial-panel-resolver > ha-panel-lovelace").shadowRoot
                  .querySelector("hui-root").shadowRoot
                  .querySelector('#layout > app-header')
            if (window.location.href.indexOf('show_tabs') > 0) {
                header = header.querySelector('app-toolbar')
            }

            const drawer = home_assistant_main.shadowRoot.querySelector("#drawer");

            header.style.display = "none";
            drawer.style.display = 'none';

            home_assistant_main.style.setProperty("--app-drawer-width", 0);
            home_assistant_main.shadowRoot
                .querySelector("#drawer > ha-sidebar").shadowRoot
                .querySelector("div.menu > paper-icon-button")
                .click();

            const view = home_assistant_main.shadowRoot
                  .querySelector("app-drawer-layout > partial-panel-resolver > ha-panel-lovelace").shadowRoot
                  .querySelector("hui-root").shadowRoot
                  .querySelector("#layout > #view")
                  .style.minHeight = "100vh";

            window.dispatchEvent(new Event('resize'));
        }
        catch (e) {
            console.log(e);
        }
    }, 500);
}