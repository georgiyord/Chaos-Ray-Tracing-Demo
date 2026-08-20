
#include "RenderEngine/Renderer.hpp"
#include "RenderEngine/Scene.hpp"
#include <RenderEngine/Matrix3x3.hpp>
#include <RenderEngine/utils.hpp>
#include <RenderEngine/vec3.hpp>
#include <iostream>

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/imgutils.h>
#include <libswscale/swscale.h>
}

#define RESOLUTION_WIDTH 960
#define RESOLUTION_HEIGHT 540
#define FRAMES_PER_SECOND 12
#define BUCKET_SIZE 12
#define MAX_RAY_DEPTH 5

struct CameraProperties {
  RenderEngine::vec3 position;
  // euler angles (i think?)
  struct {
    float pan;
    float tilt;
    float roll;
  } angles;
};

CameraProperties operator*(CameraProperties a, float b) {
  return {a.position * b,
          {a.angles.pan * b, a.angles.tilt * b, a.angles.roll * b}};
}

CameraProperties operator*(float b, CameraProperties a) { return a * b; }

CameraProperties operator-(CameraProperties a, CameraProperties b) {
  a.angles.pan = a.angles.pan < 0 ? 360 + a.angles.pan : a.angles.pan;
  b.angles.pan = b.angles.pan < 0 ? 360 + b.angles.pan : b.angles.pan;
  a.angles.tilt = a.angles.tilt < 0 ? 360 + a.angles.tilt : a.angles.tilt;
  b.angles.tilt = b.angles.tilt < 0 ? 360 + b.angles.tilt : b.angles.tilt;
  a.angles.roll = a.angles.roll < 0 ? 360 + a.angles.roll : a.angles.roll;
  b.angles.roll = b.angles.roll < 0 ? 360 + b.angles.roll : b.angles.roll;
  float pan = a.angles.pan - b.angles.pan;
  float tilt = a.angles.tilt - b.angles.tilt;
  float roll = a.angles.roll - b.angles.roll;
  if (std::abs(pan) > 180.f) {
    pan += pan < 0 ? 360.f : -360.f;
  }
  if (std::abs(tilt) > 180.f) {
    tilt += tilt < 0 ? 360.f : -360.f;
  }
  if (std::abs(roll) > 180.f) {
    roll += roll < 0 ? 360.f : -360.f;
  }
  return {a.position - b.position, {pan, tilt, roll}};
}

CameraProperties operator+(CameraProperties a, CameraProperties b) {
  return {a.position + b.position,
          {a.angles.pan + b.angles.pan, a.angles.tilt + b.angles.tilt,
           a.angles.roll + b.angles.roll}};
}

static double smoothStep(double t) {
  if (t < 0.0)
    t = 0.0;
  if (t > 1.0)
    t = 1.0;
  return t * t * t * (t * (t * 6.0 - 15.0) + 10.0);
}

static CameraProperties smoothLerp(CameraProperties a, CameraProperties b,
                                   double t) {
  return a + (b - a) * smoothStep(t);
}

[[noreturn]] void earlyTerminate(const char *msg) {
  std::cerr << "[FATAL ERROR] : " << msg << '\n';
  exit(1);
}

void checkFfmpegErr(int errc) {
  if (errc < 0) {
    char errbuf[256];
    av_strerror(errc, errbuf, sizeof(errbuf));

    earlyTerminate(errbuf);
  }
}

void renderFrame(RenderEngine::Camera &camera,
                 const RenderEngine::Renderer &renderer,
                 RenderEngine::Color *colorBuffer, size_t frameNumber) {
  // points of interest
  // 0;7;15                           in front of everything
  // -6;6;7, pan(-46)                 table -> character and object
  // -5;9;-3, tilt(-22), pan(223)     behind character -> glass and object
  // -.3;7.8;1  tilt(-50), pan(180)     glass -> object

  // 3 seconds transition
  // 1 seconds standstill at a point

  // 4 * 1 + 3 * 3 = 13 seconds

  constexpr float transitionReciprocal = 1.f / (FRAMES_PER_SECOND * 3);
  // constexpr float standstillReciprocal = 1.f / FRAMES_PER_SECOND;
  static bool standStill1_Rendered = false;
  static bool standStill2_Rendered = false;
  static bool standStill3_Rendered = false;
  static bool standStill4_Rendered = false;

  if (frameNumber < FRAMES_PER_SECOND * 1) {
    if (!standStill1_Rendered) {
      camera.updatePosition({0, 7, 15});
      std::cout << renderer.takeSnapshot(colorBuffer,
                                         RenderEngine::RenderMode::Default, 2)
                << std::endl;
      standStill1_Rendered = true;
    }
  } else if (frameNumber < FRAMES_PER_SECOND * 4) {
    CameraProperties origin;
    origin.position = {0, 7, 15};
    origin.angles = {0, 0, 0};
    CameraProperties destination;
    destination.position = {-6, 6, 7};
    destination.angles = {-46, 0, 0};

    CameraProperties positionInFrame =
        smoothLerp(origin, destination,
                   static_cast<float>(frameNumber - (FRAMES_PER_SECOND * 1)) *
                       transitionReciprocal);
    camera.updatePosition(positionInFrame.position);
    camera.updateOrientation(RenderEngine::Matrix3x3::one());
    camera.pan(positionInFrame.angles.pan);
    // camera.tilt(positionInFrame.angles.tilt);
    // camera.roll(positionInFrame.angles.roll);
    std::cout << renderer.takeSnapshot(colorBuffer,
                                       RenderEngine::RenderMode::Default, 2)
              << std::endl;
  } else if (frameNumber < FRAMES_PER_SECOND * 5) {
    if (!standStill2_Rendered) {
      camera.updatePosition({-6, 6, 7});
      camera.updateOrientation(RenderEngine::Matrix3x3::one());
      camera.pan(-46);
      std::cout << renderer.takeSnapshot(colorBuffer,
                                         RenderEngine::RenderMode::Default, 2)
                << std::endl;
      standStill2_Rendered = true;
    }
  } else if (frameNumber < FRAMES_PER_SECOND * 8) {
    CameraProperties origin;
    origin.position = {-6, 6, 7};
    origin.angles = {-46, 0, 0};
    CameraProperties destination;
    destination.position = {-5, 9, -3};
    destination.angles = {223, -22, 0};

    CameraProperties positionInFrame =
        smoothLerp(origin, destination,
                   static_cast<float>(frameNumber - (FRAMES_PER_SECOND * 5)) *
                       transitionReciprocal);
    camera.updatePosition(positionInFrame.position);
    camera.updateOrientation(RenderEngine::Matrix3x3::one());
    camera.pan(positionInFrame.angles.pan);
    camera.tilt(positionInFrame.angles.tilt);
    // camera.roll(positionInFrame.angles.roll);
    std::cout << renderer.takeSnapshot(colorBuffer,
                                       RenderEngine::RenderMode::Default, 2)
              << std::endl;
  } else if (frameNumber < FRAMES_PER_SECOND * 9) {
    if (!standStill3_Rendered) {
      camera.updatePosition({-5, 9, -3});
      camera.updateOrientation(RenderEngine::Matrix3x3::one());
      camera.pan(223);
      camera.tilt(-22);
      std::cout << renderer.takeSnapshot(colorBuffer,
                                         RenderEngine::RenderMode::Default, 2)
                << std::endl;
      standStill3_Rendered = true;
    }
  } else if (frameNumber < FRAMES_PER_SECOND * 12) {
    CameraProperties origin;
    origin.position = {-5, 9, -3};
    origin.angles = {223, -22, 0};
    CameraProperties destination;
    destination.position = {-.3f, 7.8, 1};
    destination.angles = {180, -50, 0};

    CameraProperties positionInFrame =
        smoothLerp(origin, destination,
                   static_cast<float>(frameNumber - (FRAMES_PER_SECOND * 9)) *
                       transitionReciprocal);
    camera.updatePosition(positionInFrame.position);
    camera.updateOrientation(RenderEngine::Matrix3x3::one());
    camera.pan(positionInFrame.angles.pan);
    camera.tilt(positionInFrame.angles.tilt);
    // camera.roll(positionInFrame.angles.roll);
    std::cout << renderer.takeSnapshot(colorBuffer,
                                       RenderEngine::RenderMode::Default, 2)
              << std::endl;
  } else if (frameNumber < FRAMES_PER_SECOND * 13) {
    if (!standStill4_Rendered) {
      camera.updatePosition({-.3f, 7.8, 1});
      camera.updateOrientation(RenderEngine::Matrix3x3::one());
      camera.pan(180);
      camera.tilt(-50);
      std::cout << renderer.takeSnapshot(colorBuffer,
                                         RenderEngine::RenderMode::Default, 2)
                << std::endl;
      standStill4_Rendered = true;
    }
  }
}

// TODO: should probably frames to disk and then compose them into a video, so
// that when only specific frames need to be rerendered, it won't be needed to
// render everything again

int main() {
  RenderEngine::Scene scene(RenderEngine::Scene::loadScene("scene.crtscene"));
  RenderEngine::Renderer renderer(scene);
  scene.overwriteWidth(RESOLUTION_WIDTH);
  scene.overwriteHeight(RESOLUTION_HEIGHT);
  scene.bucket_size_ = BUCKET_SIZE;
  renderer.overwriteMaxRayDepth(MAX_RAY_DEPTH);
  RenderEngine::Color *colorBuffer = renderer.createColorBuffer();
  const char *filename = "renderedDemo.mp4";

  // init ffmpeg things
  AVFormatContext *containerContext = nullptr;
  int errc = avformat_alloc_output_context2(&containerContext, nullptr, "mp4",
                                            filename);
  checkFfmpegErr(errc);

  const AVCodec *codec = avcodec_find_encoder(AV_CODEC_ID_H264);
  if (!codec) {
    earlyTerminate("Could not find codec?");
  }

  AVStream *stream = avformat_new_stream(containerContext, nullptr);
  if (!stream) {
    earlyTerminate("Failed to allocate new stream");
  }
  stream->id = containerContext->nb_streams - 1;

  AVCodecContext *codecCtx = avcodec_alloc_context3(codec);
  if (!codecCtx) {
    earlyTerminate("Failed to allocate codec context");
  }

  codecCtx->codec_id = AV_CODEC_ID_H264;
  codecCtx->bit_rate = 0; // Handled dynamically via CRF
  codecCtx->width = 1920;
  codecCtx->height = 1080;
  codecCtx->time_base = AVRational{1, FRAMES_PER_SECOND};
  codecCtx->framerate = AVRational{FRAMES_PER_SECOND, 1};
  codecCtx->gop_size = FRAMES_PER_SECOND / 2; // Keyframe interval
  codecCtx->pix_fmt = AV_PIX_FMT_YUV420P; // Required layout for generic players

  codecCtx->flags |= AV_CODEC_FLAG_GLOBAL_HEADER;

  AVDictionary *codec_opts = nullptr;

  av_dict_set(&codec_opts, "preset", "medium", 0);
  av_dict_set(&codec_opts, "crf", "18", 0);
  av_dict_set(&codec_opts, "tune", "animation", 0);
  av_dict_set(&codec_opts, "qp", "0", 0);

  errc = avcodec_open2(codecCtx, codec, &codec_opts);
  checkFfmpegErr(errc);

  av_dict_free(&codec_opts);

  errc = avcodec_parameters_from_context(stream->codecpar, codecCtx);
  checkFfmpegErr(errc);

  stream->time_base = codecCtx->time_base;

  if (!(containerContext->oformat->flags & AVFMT_NOFILE)) {
    errc = avio_open(&containerContext->pb, filename, AVIO_FLAG_WRITE);
    checkFfmpegErr(errc);
  }

  AVDictionary *muxerOpts = nullptr;
  av_dict_set(&muxerOpts, "movflags", "+faststart", 0);
  errc = avformat_write_header(containerContext, &muxerOpts);
  checkFfmpegErr(errc);
  av_dict_free(&muxerOpts);

  AVFrame *src_frame = av_frame_alloc();
  src_frame->format = AV_PIX_FMT_RGBF32LE;
  src_frame->width = RESOLUTION_WIDTH;
  src_frame->height = RESOLUTION_HEIGHT;

  AVFrame *dst_frame = av_frame_alloc();
  dst_frame->format = codecCtx->pix_fmt;
  dst_frame->width = 1920;
  dst_frame->height = 1080;
  errc = av_frame_get_buffer(dst_frame, 0);
  checkFfmpegErr(errc);

  SwsContext *swsContex = sws_getContext(
      RESOLUTION_WIDTH, RESOLUTION_HEIGHT, AV_PIX_FMT_RGBF32LE, 1920, 1080,
      codecCtx->pix_fmt, SWS_POINT, nullptr, nullptr, nullptr);
  if (!swsContex) {
    earlyTerminate("Could not initialize scaling context");
  }

  AVPacket *pkt = av_packet_alloc();

  auto encode_frame = [&](AVFrame *frame) {
    int response = avcodec_send_frame(codecCtx, frame);
    if (response < 0)
      return;

    while (response >= 0) {
      response = avcodec_receive_packet(codecCtx, pkt);
      if (response == AVERROR(EAGAIN) || response == AVERROR_EOF) {
        break;
      } else if (response < 0) {
        checkFfmpegErr(response);
      }

      av_packet_rescale_ts(pkt, codecCtx->time_base, stream->time_base);
      pkt->stream_index = stream->index;

      av_interleaved_write_frame(containerContext, pkt);
      av_packet_unref(pkt);
    }
  };

  // RENDER STAGE

  std::vector<float> rgb_buffer(RESOLUTION_WIDTH * RESOLUTION_HEIGHT * 3);
  size_t total_frames = FRAMES_PER_SECOND * 13;

  for (int i = 0; i < total_frames; ++i) {
    renderFrame(scene.camera(), renderer, colorBuffer, i);

    src_frame->data[0] = reinterpret_cast<uint8_t *>(colorBuffer);
    src_frame->linesize[0] = RESOLUTION_WIDTH * 3 * sizeof(float);

    sws_scale(swsContex, src_frame->data, src_frame->linesize, 0,
              RESOLUTION_HEIGHT, dst_frame->data, dst_frame->linesize);

    dst_frame->pts = i;

    std::cout << "Encoding frame " << (i + 1) << "/" << total_frames
              << std::endl;
    encode_frame(dst_frame);
  }
  std::cout << std::endl;

  // cleanup

  encode_frame(nullptr);

  av_write_trailer(containerContext);

  av_frame_free(&src_frame);
  av_frame_free(&dst_frame);
  av_packet_free(&pkt);
  avcodec_free_context(&codecCtx);
  sws_freeContext(swsContex);

  avio_closep(&containerContext->pb);
  avformat_free_context(containerContext);

  std::cout << "Success! Saved output to " << filename << std::endl;
  return 0;
}