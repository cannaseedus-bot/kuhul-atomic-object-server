/* GhostKUHUL: The bridge between Symbolic Logic and Kinetic Force 
   Usage: Bind this to your Canvas Runtime to enable 'Physical Intent'
*/

((opts) => {
  const GHOST_VERSION = "0.8.2-π";
  
  class GhostKUHULAdapter {
    constructor(config) {
      this.kernel = config.kernel; // The π-Solver
      this.registry = new Map();   // Mapping Glyph IDs to π-Bodies
    }

    // Binds a ⟁tree node to a %pi.body
    bind(glyphId, bodyId) {
      const body = this.kernel.getBody(bodyId);
      if (body) {
        this.registry.set(glyphId, body);
        console.log(`[Ghost] Bound Glyph ${glyphId} to Body ${bodyId}`);
      }
    }

    // Executes a Symbolic Command as a Physical Impulse
    // e.g., execute("⟁jump", { magnitude: 500 })
    execute(glyphIntent, params = {}) {
      const targetBody = this.registry.get(glyphIntent);
      if (!targetBody) return;

      switch(glyphIntent) {
        case "⟁jump":
          this.kernel.applyImpulse(targetBody, [0, -params.magnitude || 100, 0]);
          break;
        case "⟁attract":
          this.kernel.applyForceTowards(targetBody, params.origin, params.strength);
          break;
        case "⟁stabilize":
          targetBody.velocity = [0, 0, 0];
          targetBody.rotation = [0, 0, 0, 1];
          break;
      }
    }
  }

  window.GhostKUHUL = {
    create(opts) { return new GhostKUHULAdapter(opts); }
  };
})();