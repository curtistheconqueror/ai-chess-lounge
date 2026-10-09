import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { SoundLab } from "./SoundLab";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {window.location.pathname === "/sound-lab" ? <SoundLab /> : <App />}
  </React.StrictMode>,
);
