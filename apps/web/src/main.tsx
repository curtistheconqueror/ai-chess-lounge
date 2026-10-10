import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { SoundLab } from "./SoundLab";
import { BoardStudio } from "./BoardStudio";
import "./styles.css";

if ("serviceWorker" in navigator && window.isSecureContext && import.meta.env.PROD) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" }).catch(() => {
      // Installation is optional; ordinary online play must remain available.
    });
  });
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {window.location.pathname === "/sound-lab" ? <SoundLab />
      : window.location.pathname === "/board-studio" ? <BoardStudio /> : <App />}
  </React.StrictMode>,
);
