{{flutter_js}}
{{flutter_build_config}}

// Load the renderer from this installation, never the public Flutter CDN.
_flutter.loader.load({
  config: {
    canvasKitBaseUrl: new URL('canvaskit/', document.baseURI).href,
    fontFallbackBaseUrl: new URL('assets/fonts/', document.baseURI).href,
  },
  onEntrypointLoaded: async function (engineInitializer) {
    try {
      const appRunner = await engineInitializer.initializeEngine();
      await appRunner.runApp();
    } catch (error) {
      window.showStartupFailure();
      console.error('Application startup failed:', error);
    }
  },
}).catch((error) => {
  window.showStartupFailure();
  console.error('Flutter loader failed:', error);
});
