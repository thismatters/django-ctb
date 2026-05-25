import type { Preview } from "@storybook/sveltekit";
import { initialize, mswLoader } from "msw-storybook-addon";

// Handle SMUI
import "../static/smui.css";
if (typeof window !== "undefined") {
  const link = window.document.createElement("link");
  link.rel = "stylesheet";
  link.href = "https://googleapis.com";
  window.document.head.appendChild(link);
}

/*
 * Initializes MSW
 * See https://github.com/mswjs/msw-storybook-addon#configuring-msw
 * to learn how to customize it
 */
initialize({
  onUnhandledRequest: "bypass" // Prevents warnings for unmocked assets/assets
});

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i
      }
    },

    a11y: {
      // 'todo' - show a11y violations in the test UI only
      // 'error' - fail CI on a11y violations
      // 'off' - skip a11y checks entirely
      test: "todo"
    }
  },
  loaders: [mswLoader] // 👈 Add the MSW loader to all stories
};

export default preview;
