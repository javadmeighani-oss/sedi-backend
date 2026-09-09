# google-services.json (FCM on real device)

For **FCM token retrieval on a real device**, you must provide a valid `google-services.json` from your Firebase project.

- **Location:** Place the file here: `android/app/google-services.json`
- **Source:** Firebase Console → Project settings → Your apps → Android app with **package name `com.sedi.app`** → Download `google-services.json`
- **Do not commit** the real file (it is in `.gitignore`). Do not invent or paste API keys into the repo.
- **CI builds** use the placeholder `google-services.json.ci` so the Gradle plugin succeeds; that placeholder is not valid for runtime FCM on device.

Without a valid `google-services.json` in this directory, local/device builds may fail at runtime with:  
`[firebase_messaging/unknown] Please set a valid API key.`
