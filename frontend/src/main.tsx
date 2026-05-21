import React from "react";
import ReactDOM from "react-dom/client";
import { NeoProvider } from "neobrutalistcomponents";
import "neobrutalistcomponents/neobrutalistcomponents.css";
import "neobrutalistcomponents/themes/swiss.css";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <NeoProvider theme="swiss">
      <App />
    </NeoProvider>
  </React.StrictMode>,
);
