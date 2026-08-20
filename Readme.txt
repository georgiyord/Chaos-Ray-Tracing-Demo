A demo animation, created using github.com/georgiyord/Chaos-Ray-Tracing and Ffmpeg

Contents:
    Blender scene
    A blender plugin for exporting scenes to .crtscene format, readable by the ray tracer
    Textures used in the animation
    credits.txt, with links to all public assets used in the animation
    main.cpp -> the program that creates the animation
    debugTool.cpp -> a program that renders a frame on an opengl window, where settings can be passed at runtime with an imgui window
    personal-use builder scripts for the programs


The scene features the following objects:
    a plane floor
    a chair with albedo texture
    a humanoid character sitting on the chair. Some of the clothes have a bitmap texture
    a table compromised of 4 legs and a top. the legs have a bitmap texture
    a skybox
    a monkey head (Blender test object) with a reflective material and an albedo of 0.5 on all channels
    a magnifying glass with a convex lens-like object, with a refractive material, held and pointed at the monkey head by the character

The scene is rendered without global illumination

The blender plugin is made by an LLM agent and does not work perfectly. Using it on the blender scene will not produce the same scene.crtscene as in the repository, as manual changes and fixes have been made
debugTool.cpp was build on top of imgui/examples/example_glfw_opengl3. Due to inexpirience with OpenGL and GLFW and lack of time, an LLM agent was used to reshape most of it

IMPORTANT
If building manually:
    main.cpp:       you need to pass libraries to the ray tracer and ffmpeg
    debugTool.cpp:  you need to pass libraries to the ray tracer, opengl and glfw. Imgui is provided as a submodule to the repository

A dynamic library can be build for the ray tracer with `make libDebug/libRelease/libReleaseWithSymbols` from it's own repository.
