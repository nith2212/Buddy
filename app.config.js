// Extends app.json. google-services.json (Firebase config for push) is gitignored, so EAS cloud builds
// get it from the secret file variable GOOGLE_SERVICES_JSON (eas env); local runs use the local file.
module.exports = ({ config }) => ({
  ...config,
  android: {
    ...config.android,
    googleServicesFile: process.env.GOOGLE_SERVICES_JSON ?? './google-services.json',
  },
});
