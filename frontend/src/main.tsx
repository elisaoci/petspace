import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./app/App";
import { AuthProvider } from "./context/AuthContext";
import { PetProvider } from "./context/PetContext";
import { registerServiceWorker } from "./lib/registerServiceWorker";
import "./styles/index.css";

registerServiceWorker();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <PetProvider>
          <App />
        </PetProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
