// Dear ImGui: standalone example application for GLFW + OpenGL 3, using programmable pipeline
// (GLFW is a cross-platform general purpose library for handling windows, inputs, OpenGL/Vulkan/Metal graphics context creation, etc.)

// Learn about Dear ImGui:
// - FAQ                  https://dearimgui.com/faq
// - Getting Started      https://dearimgui.com/getting-started
// - Documentation        https://dearimgui.com/docs (same as your local docs/ folder).
// - Introduction, links and more at the top of imgui.cpp

#include "imgui.h"
#include "imgui_impl_glfw.h"
#include "imgui_impl_opengl3.h"
#include <chrono>
#include <vector>
#include <thread>
#include <atomic>
#include <cmath>
#include <numbers>
#include <stdio.h>
#define GL_SILENCE_DEPRECATION
// Expose modern GL functions (glCreateShader, glGenVertexArrays, glBufferData, ...)
// from the system GL headers, needed for the fullscreen quad.
#define GL_GLEXT_PROTOTYPES
#if defined(IMGUI_IMPL_OPENGL_ES2)
#include <GLES2/gl2.h>
#endif
#include <GLFW/glfw3.h> // Will drag system OpenGL headers

// [Win32] Our example includes a copy of glfw3.lib pre-compiled with VS2010 to maximize ease of testing and compatibility with old VS compilers.
// To link with VS2010-era libraries, VS2015+ requires linking with legacy_stdio_definitions.lib, which we do using this pragma.
// Your own project should not be affected, as you are likely to link with a newer binary of GLFW that is adequate for your version of Visual Studio.
#if defined(_MSC_VER) && (_MSC_VER >= 1900) && !defined(IMGUI_DISABLE_WIN32_FUNCTIONS)
#pragma comment(lib, "legacy_stdio_definitions")
#endif

// This example can also compile and run with Emscripten! See 'Makefile.emscripten' for details.
#ifdef __EMSCRIPTEN__
#include "../libs/emscripten/emscripten_mainloop_stub.h"
#endif

#include "RenderEngine/Scene.hpp"
#include "RenderEngine/Renderer.hpp"

static void glfw_error_callback(int error, const char* description)
{
    fprintf(stderr, "GLFW Error %d: %s\n", error, description);
}


static GLuint compileShader(GLenum type, const char* src)
{
    GLuint shader = glCreateShader(type);
    glShaderSource(shader, 1, &src, nullptr);
    glCompileShader(shader);
    GLint ok = GL_FALSE;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
    if (ok == GL_FALSE)
    {
        char log[512];
        glGetShaderInfoLog(shader, (GLsizei)sizeof(log), nullptr, log);
        fprintf(stderr, "Error compiling shader: %s\n", log);
        glDeleteShader(shader);
        return 0;
    }
    return shader;
}

static GLuint linkProgram(const char* vsSrc, const char* fsSrc)
{
    GLuint vs = compileShader(GL_VERTEX_SHADER, vsSrc);
    GLuint fs = compileShader(GL_FRAGMENT_SHADER, fsSrc);
    GLuint program = glCreateProgram();
    glAttachShader(program, vs);
    glAttachShader(program, fs);
    glLinkProgram(program);
    GLint ok = GL_FALSE;
    glGetProgramiv(program, GL_LINK_STATUS, &ok);
    if (ok == GL_FALSE)
    {
        char log[512];
        glGetProgramInfoLog(program, (GLsizei)sizeof(log), nullptr, log);
        fprintf(stderr, "Error linking program: %s\n", log);
    }
    glDeleteShader(vs);
    glDeleteShader(fs);
    return program;
}

// Main code
int main(int, char**)
{
    glfwSetErrorCallback(glfw_error_callback);
    if (!glfwInit())
        return 1;

    // Select GL version + let the backend select a GLSL version
    const char* glsl_version = nullptr;
#if defined(IMGUI_IMPL_OPENGL_ES2)
    // GL ES 2.0 + GLSL 100 (WebGL 1.0)
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 2);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 0);
    glfwWindowHint(GLFW_CLIENT_API, GLFW_OPENGL_ES_API);
#elif defined(IMGUI_IMPL_OPENGL_ES3)
    // GL ES 3.0 + GLSL 300 es (WebGL 2.0)
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 0);
    glfwWindowHint(GLFW_CLIENT_API, GLFW_OPENGL_ES_API);
#elif defined(__APPLE__)
    // GL 3.2 + generally GLSL 150
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 2);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);  // 3.2+ only
    glfwWindowHint(GLFW_OPENGL_FORWARD_COMPAT, GL_TRUE);            // Required on Mac
#else
    // GL 3.0 + generally GLSL 130
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 0);
    //glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);  // 3.2+ only
    //glfwWindowHint(GLFW_OPENGL_FORWARD_COMPAT, GL_TRUE);            // 3.0+ only
#endif

    // Create window with graphics context
    float main_scale = ImGui_ImplGlfw_GetContentScaleForMonitor(glfwGetPrimaryMonitor()); // Valid on GLFW 3.3+ only
    GLFWwindow* window = glfwCreateWindow((int)(1280 * main_scale), (int)(800 * main_scale), "Dear ImGui GLFW+OpenGL3 example", nullptr, nullptr);
    if (window == nullptr)
        return 1;
    glfwMakeContextCurrent(window);
    glfwSwapInterval(1); // Enable vsync

    // Setup Dear ImGui context
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGuiIO& io = ImGui::GetIO(); (void)io;
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard;     // Enable Keyboard Controls
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableGamepad;      // Enable Gamepad Controls

    // Setup Dear ImGui style
    ImGui::StyleColorsDark();
    //ImGui::StyleColorsLight();

    // Setup scaling
    ImGuiStyle& style = ImGui::GetStyle();
    style.ScaleAllSizes(main_scale);        // Bake a fixed style scale. (until we have a solution for dynamic style scaling, changing this requires resetting Style + calling this again)
    style.FontScaleDpi = main_scale;        // Set initial font scale. (in docking branch: using io.ConfigDpiScaleFonts=true automatically overrides this for every window depending on the current monitor)

    // Setup Platform/Renderer backends
    ImGui_ImplGlfw_InitForOpenGL(window, true);
#ifdef __EMSCRIPTEN__
    ImGui_ImplGlfw_InstallEmscriptenCallbacks(window, "#canvas");
#endif
    ImGui_ImplOpenGL3_Init(glsl_version);

    // Load Fonts
    // - If fonts are not explicitly loaded, Dear ImGui will select an embedded font: either AddFontDefaultVector() or AddFontDefaultBitmap().
    //   This selection is based on (style.FontSizeBase * style.FontScaleMain * style.FontScaleDpi) reaching a small threshold.
    // - You can load multiple fonts and use ImGui::PushFont()/PopFont() to select them.
    // - If a file cannot be loaded, AddFont functions will return a nullptr. Please handle those errors in your code (e.g. use an assertion, display an error and quit).
    // - Read 'docs/FONTS.md' for more instructions and details.
    // - Use '#define IMGUI_ENABLE_FREETYPE' in your imconfig file to use FreeType for higher quality font rendering.
    // - Remember that in C/C++ if you want to include a backslash \ in a string literal you need to write a double backslash \\ !
    // - Our Emscripten build process allows embedding fonts to be accessible at runtime from the "fonts/" folder. See Makefile.emscripten for details.
    //style.FontSizeBase = 20.0f;
    //io.Fonts->AddFontDefaultVector();
    //io.Fonts->AddFontDefaultBitmap();
    //io.Fonts->AddFontFromFileTTF("c:\\Windows\\Fonts\\segoeui.ttf");
    //io.Fonts->AddFontFromFileTTF("../../misc/fonts/DroidSans.ttf");
    //io.Fonts->AddFontFromFileTTF("../../misc/fonts/Roboto-Medium.ttf");
    //io.Fonts->AddFontFromFileTTF("../../misc/fonts/Cousine-Regular.ttf");
    //ImFont* font = io.Fonts->AddFontFromFileTTF("c:\\Windows\\Fonts\\ArialUni.ttf");
    //IM_ASSERT(font != nullptr);

    // Our state
    bool show_demo_window = true;
    bool show_another_window = false;
    ImVec4 clear_color = ImVec4(0.45f, 0.55f, 0.60f, 1.00f);


    RenderEngine::Scene scene(RenderEngine::Scene::loadScene("scene.crtscene"));
    RenderEngine::Renderer renderer(scene);
    scene.overwriteWidth(120);
    scene.overwriteHeight(120);

    RenderEngine::RenderMode renderMode = RenderEngine::RenderMode::GoochShade;

    // Double-buffered render targets: the background thread renders into
    // backBuffer, which is swapped into frontBuffer once complete. The main
    // thread only ever touches frontBuffer (no data races).
    RenderEngine::Color* frontBuffer = renderer.createColorBuffer();
    RenderEngine::Color* backBuffer = renderer.createColorBuffer();

    // Background render job state. frameReady is set by the render thread once
    // a finished frame has been swapped into frontBuffer.
    std::thread renderThread;
    bool rendering = false;
    std::atomic<bool> frameReady{false};

    std::chrono::milliseconds lastRenderTime{0};

    // Editable camera position, initialized from the scene's camera.
    float camPos[3] = {
        (float)scene.camera().position().x_,
        (float)scene.camera().position().y_,
        (float)scene.camera().position().z_,
    };

    float tiltDeg = 0.f, panDeg = 0.f, rollDeg = 0.f;

    const RenderEngine::Matrix3x3 baseOrientation = scene.camera().orientation();

    int renderW = (int)scene.width_;
    int renderH = (int)scene.height_;

    int renderBucket = (int)scene.bucket_size_;

    int renderRayDepth = 5;

    int raySamplesPerPixel = 1;

    static const char* renderModeNames[] = {
        "Default", "Normal", "Distance", "Gooch", "Barycentric"};
    int renderModeIdx = 3; // GoochShade

    // CPU-side RGB buffer, resized to match the current resolution.
    std::vector<float> rgb_buffer;

    // Create the GPU texture object (filled by uploadRenderToTexture).
    GLuint textureID;
    glGenTextures(1, &textureID);
    glBindTexture(GL_TEXTURE_2D, textureID);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glBindTexture(GL_TEXTURE_2D, 0);

    // Convert the renderer's Color buffer to RGB floats and upload it to the
    // GPU texture. Called at startup and again whenever the ImGui menu triggers
    // a re-render.
    auto uploadRenderToTexture = [&]() {
        const size_t pixelCount = (size_t)scene.width_ * scene.height_;
        rgb_buffer.resize(pixelCount * 3);
        for (size_t i = 0; i < pixelCount; ++i){
            rgb_buffer[i * 3 + 0] = frontBuffer[i].red();
            rgb_buffer[i * 3 + 1] = frontBuffer[i].green();
            rgb_buffer[i * 3 + 2] = frontBuffer[i].blue();
        }
        glBindTexture(GL_TEXTURE_2D, textureID);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, (GLsizei)scene.width_, (GLsizei)scene.height_, 0, GL_RGB, GL_FLOAT, rgb_buffer.data());
        glBindTexture(GL_TEXTURE_2D, 0);
    };

    // Initial render -> texture upload.
    uploadRenderToTexture();

    // ---- Fullscreen quad: draws the render texture onto the main GLFW window ----
    const char* quadVertexShaderSrc = R"(
#version 130
in vec2 aPos;
in vec2 aUV;
out vec2 vUV;
void main()
{
    vUV = aUV;
    gl_Position = vec4(aPos, 0.0, 1.0);
}
)";
    const char* quadFragmentShaderSrc = R"(
#version 130
uniform sampler2D uTex;
in vec2 vUV;
out vec4 fragColor;
void main()
{
    // The renderer's buffer is top-down (row 0 = top), OpenGL textures are
    // bottom-up (v = 0 at the bottom), so flip v when sampling.
    fragColor = texture(uTex, vec2(vUV.x, 1.0 - vUV.y));
}
)";

    GLuint quadProgram = linkProgram(quadVertexShaderSrc, quadFragmentShaderSrc);

    // Fullscreen quad geometry (2 triangles covering NDC [-1, 1])
    const float quadVertices[] = {
        //  x     y     u    v
        -1.f, -1.f, 0.f, 0.f,
         1.f, -1.f, 1.f, 0.f,
         1.f,  1.f, 1.f, 1.f,
        -1.f, -1.f, 0.f, 0.f,
         1.f,  1.f, 1.f, 1.f,
        -1.f,  1.f, 0.f, 1.f,
    };
    GLuint quadVAO = 0, quadVBO = 0;
    glGenVertexArrays(1, &quadVAO);
    glGenBuffers(1, &quadVBO);
    glBindVertexArray(quadVAO);
    glBindBuffer(GL_ARRAY_BUFFER, quadVBO);
    glBufferData(GL_ARRAY_BUFFER, sizeof(quadVertices), quadVertices, GL_STATIC_DRAW);
    GLint aPos = glGetAttribLocation(quadProgram, "aPos");
    GLint aUV  = glGetAttribLocation(quadProgram, "aUV");
    glEnableVertexAttribArray((GLuint)aPos);
    glVertexAttribPointer((GLuint)aPos, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(float), (void*)0);
    glEnableVertexAttribArray((GLuint)aUV);
    glVertexAttribPointer((GLuint)aUV, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(float), (void*)(2 * sizeof(float)));
    glBindVertexArray(0);



    // Main loop
    while (!glfwWindowShouldClose(window))
    {
        // Poll and handle events (inputs, window resize, etc.)
        // You can read the io.WantCaptureMouse, io.WantCaptureKeyboard flags to tell if dear imgui wants to use your inputs.
        // - When io.WantCaptureMouse is true, do not dispatch mouse input data to your main application, or clear/overwrite your copy of the mouse data.
        // - When io.WantCaptureKeyboard is true, do not dispatch keyboard input data to your main application, or clear/overwrite your copy of the keyboard data.
        // Generally you may always pass all inputs to dear imgui, and hide them from your application based on those two flags.
        glfwPollEvents();
        if (glfwGetWindowAttrib(window, GLFW_ICONIFIED) != 0)
        {
            ImGui_ImplGlfw_Sleep(10);
            continue;
        }

        // If the background render finished, join it and upload the new frame.
        if (frameReady.exchange(false)) {
            if (renderThread.joinable())
                renderThread.join();
            rendering = false;
            uploadRenderToTexture();
        }

        // Start the Dear ImGui frame
        ImGui_ImplOpenGL3_NewFrame();
        ImGui_ImplGlfw_NewFrame();
        ImGui::NewFrame();

        // 2.5 Render controls: camera position/orientation + resolution.
        //     Re-render runs on a background thread; the UI stays responsive.
        {
            ImGui::Begin("Render Controls");
            ImGui::DragFloat3("Position", camPos, 0.1f);
            ImGui::Separator();
            ImGui::Text("Orientation (degrees from initial)");
            ImGui::DragFloat("Pan",  &panDeg, 0.5f, -360.f, 360.f);
            ImGui::DragFloat("Tilt", &tiltDeg, 0.5f, -360.f, 360.f);
            ImGui::DragFloat("Roll", &rollDeg, 0.5f, -360.f, 360.f);
            ImGui::Separator();
            ImGui::Text("Resolution");
            ImGui::InputInt("Width", &renderW, 8, 64);
            ImGui::InputInt("Height", &renderH, 8, 64);
            ImGui::InputInt("Bucket Size", &renderBucket, 1, 64);
            ImGui::InputInt("Max Ray Depth", &renderRayDepth, 1, 32);
            ImGui::Separator();
            ImGui::Text("Render Mode");
            if (ImGui::Combo("Mode", &renderModeIdx, renderModeNames,
                             IM_ARRAYSIZE(renderModeNames))) {
                switch (renderModeIdx) {
                    case 0: renderMode = RenderEngine::RenderMode::Default; break;
                    case 1: renderMode = RenderEngine::RenderMode::NormalShade; break;
                    case 2: renderMode = RenderEngine::RenderMode::DistanceShade; break;
                    case 3: renderMode = RenderEngine::RenderMode::GoochShade; break;
                    case 4: renderMode = RenderEngine::RenderMode::BarycentricShade; break;
                }
            }
            ImGui::InputInt("Ray SPP", &raySamplesPerPixel, 1, 1);
            ImGui::BeginDisabled(rendering);
            const bool clickedReRender = ImGui::Button("Re-render");
            ImGui::EndDisabled();
            if (rendering) {
                ImGui::SameLine();
                ImGui::Text("Rendering...");
            }
            if (lastRenderTime.count() >= 1000) {
                ImGui::Text("Last render: %.2f s", lastRenderTime.count() / 1000.0);
            } else if (lastRenderTime.count() > 0) {
                ImGui::Text("Last render: %lld ms", (long long)lastRenderTime.count());
            }
            if (clickedReRender)
            {
                // Apply resolution; re-allocate both buffers only if it changed.
                // (Only reachable while idle, so no render thread is reading
                //  the scene or the buffers.)
                if (renderW < 1) renderW = 1;
                if (renderH < 1) renderH = 1;
                if ((size_t)renderW != scene.width_ || (size_t)renderH != scene.height_) {
                    scene.overwriteWidth((size_t)renderW);
                    scene.overwriteHeight((size_t)renderH);
                    delete[] frontBuffer;
                    delete[] backBuffer;
                    frontBuffer = renderer.createColorBuffer();
                    backBuffer = renderer.createColorBuffer();
                }
                // takeSnapshot throws unless width/height are multiples of
                // bucket_size (which would crash the render thread), so snap
                // the entered value to the largest divisor of both.
                if (renderBucket < 1) renderBucket = 1;
                while (renderBucket > 1 &&
                       ((size_t)renderW % renderBucket != 0 ||
                        (size_t)renderH % renderBucket != 0))
                    --renderBucket;
                scene.bucket_size_ = (size_t)renderBucket;
                if (renderRayDepth < 1) renderRayDepth = 1;
                renderer.overwriteMaxRayDepth((size_t)renderRayDepth);
                scene.camera().updatePosition(RenderEngine::vec3(camPos[0], camPos[1], camPos[2]));

                const float toRad = std::numbers::pi / 180.0;
                const float cT = std::cos(tiltDeg * toRad);
                const float sT = std::sin(tiltDeg * toRad);
                const float cP = std::cos(panDeg  * toRad);
                const float sP = std::sin(panDeg  * toRad);
                const float cR = std::cos(rollDeg * toRad);
                const float sR = std::sin(rollDeg * toRad);

                const RenderEngine::Matrix3x3 rotX{{1, 0, 0, 0, cT, sT, 0, -sT, cT}}; // tilt: world X
                const RenderEngine::Matrix3x3 rotY{{cP, 0, -sP, 0, 1, 0, sP, 0, cP}}; // pan:  world Y (up)
                const RenderEngine::Matrix3x3 rotZ{{cR, sR, 0, -sR, cR, 0, 0, 0, 1}}; // roll: world Z

                RenderEngine::Matrix3x3 orient = baseOrientation * rotX * rotY * rotZ;
                scene.camera().updateOrientation(orient);
                // Kick off the render on a background thread.
                rendering = true;
                renderThread = std::thread([&]() {
                    lastRenderTime = renderer.takeSnapshot(backBuffer, renderMode, raySamplesPerPixel);
                    std::swap(frontBuffer, backBuffer);
                    frameReady.store(true);
                });
            }
            ImGui::End();
        }

        // Rendering
        ImGui::Render();
        int display_w, display_h;
        glfwGetFramebufferSize(window, &display_w, &display_h);
        glViewport(0, 0, display_w, display_h);
        glClearColor(clear_color.x * clear_color.w, clear_color.y * clear_color.w, clear_color.z * clear_color.w, clear_color.w);
        glClear(GL_COLOR_BUFFER_BIT);

        // Draw the render buffer across the whole GLFW window (main framebuffer)
        glUseProgram(quadProgram);
        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, textureID);
        glUniform1i(glGetUniformLocation(quadProgram, "uTex"), 0);
        glBindVertexArray(quadVAO);
        glDrawArrays(GL_TRIANGLES, 0, 6);
        glBindVertexArray(0);

        ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());

        glfwSwapBuffers(window);
    }
#ifdef __EMSCRIPTEN__
    EMSCRIPTEN_MAINLOOP_END;
#endif

    // Cleanup
    ImGui_ImplOpenGL3_Shutdown();
    ImGui_ImplGlfw_Shutdown();
    ImGui::DestroyContext();

    glfwDestroyWindow(window);
    glfwTerminate();

    // Wait for any in-flight render before freeing the buffers.
    if (renderThread.joinable())
        renderThread.join();

    delete[] frontBuffer;
    delete[] backBuffer;

    return 0;
}
