{
  description = "A very basic flake";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
    RenderEngine.url = "github:georgiyord/Chaos-Ray-Tracing";
  };

  outputs =
    inputs:
    let
      pkgs = inputs.nixpkgs.legacyPackages.x86_64-linux;
    in
    {
      devShells.x86_64-linux.default = pkgs.mkShell {
        packages = with pkgs; [
          pkg-config
          (ffmpeg-headless.override { withLib = true; })
          glfw3
          imgui
          vulkan-loader
          vulkan-headers
          bear
          inputs.RenderEngine.packages.x86_64-linux.RenderEngine
        ];
        # inputsFrom = with pkgs; [
        # ];
        shellHook = ''
          export DEBUG=1
          export NIX_ENFORCE_NO_NATIVE=0
        '';
      };
    };
}
