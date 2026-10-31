import nextConfig from "eslint-config-next";

export default [
  {
    ignores: ["coverage/**", ".next/**", "eslint.config.mjs"],
  },
  ...nextConfig,
  {
    linterOptions: {
      reportUnusedDisableDirectives: false,
    },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "react-hooks/set-state-in-effect": "off",
      "import/no-anonymous-default-export": "off"
    }
  }
];
