import 'dart:io';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';
import 'package:video_player/video_player.dart';

void main() {
  runApp(const MaterialApp(
    home: VideoGeneratorScreen(),
    debugShowCheckedModeBanner: false,
  ));
}

class VideoGeneratorScreen extends StatefulWidget {
  const VideoGeneratorScreen({super.key});

  @override
  State<VideoGeneratorScreen> createState() => _VideoGeneratorScreenState();
}

class _VideoGeneratorScreenState extends State<VideoGeneratorScreen> {
  // Pre-filled with your permanent Render URL
  final TextEditingController _urlController =
      TextEditingController(text: "https://ai-video-apk.onrender.com");
  final TextEditingController _scriptController = TextEditingController();

  String _aspectRatio = "9:16";
  String _selectedVoice = "ta-IN-PallaviNeural";
  String _avatarSource = "Cartoons"; // "Cartoons" or "Gallery"
  int _selectedCartoonIndex = 0;
  File? _galleryImage;

  bool _isLoading = false;
  String _statusMsg = "";
  File? _generatedVideoFile;
  VideoPlayerController? _videoPlayerController;

  final List<String> _stockAvatars = [
    "https://cdn.pixabay.com/photo/2016/08/20/05/38/avatar-1606916_1280.png",
    "https://cdn.pixabay.com/photo/2014/04/03/10/32/businessman-310819_1280.png",
    "https://cdn.pixabay.com/photo/2017/01/31/19/07/avatar-2026510_1280.png"
  ];

  final Map<String, String> _voices = {
    "Tamil (Female - Pallavi)": "ta-IN-PallaviNeural",
    "Tamil (Male - Valluvar)": "ta-IN-ValluvarNeural",
    "Indian English / Bilingual (Female - Neerja)": "en-IN-NeerjaNeural",
    "Indian English / Bilingual (Male - Prabhat)": "en-IN-PrabhatNeural",
    "English (US Female - Jenny)": "en-US-JennyNeural",
    "English (US Male - Guy)": "en-US-GuyNeural"
  };

  @override
  void dispose() {
    _videoPlayerController?.dispose();
    _urlController.dispose();
    _scriptController.dispose();
    super.dispose();
  }

  void _resetForNextVideo() {
    setState(() {
      _videoPlayerController?.pause();
      _videoPlayerController?.dispose();
      _videoPlayerController = null;
      _generatedVideoFile = null;
      _statusMsg = "";
    });
  }

  Future<void> _pickGalleryImage() async {
    final picker = ImagePicker();
    final picked = await picker.pickImage(source: ImageSource.gallery);
    if (picked != null) {
      setState(() => _galleryImage = File(picked.path));
    }
  }

  Future<void> _generateVideo() async {
    if (_urlController.text.trim().isEmpty) {
      setState(() => _statusMsg = "Please enter a Server URL.");
      return;
    }

    setState(() {
      _isLoading = true;
      _statusMsg = "Generating cinematic scenes, voice & lip-sync...";
      _videoPlayerController?.dispose();
      _videoPlayerController = null;
      _generatedVideoFile = null;
    });

    try {
      final baseUri = _urlController.text.trim().replaceAll(RegExp(r'/+$'), '');
      final uri = Uri.parse("$baseUri/generate");
      final request = http.MultipartRequest("POST", uri);

      request.fields['aspect_ratio'] = _aspectRatio;
      request.fields['voice'] = _selectedVoice;
      request.fields['script'] = _scriptController.text.trim();

      if (_avatarSource == "Cartoons") {
        request.fields['image_mode'] = "stock_cartoon";
        request.fields['stock_image_url'] = _stockAvatars[_selectedCartoonIndex];
      } else if (_avatarSource == "Gallery" && _galleryImage != null) {
        request.fields['image_mode'] = "upload";
        request.files.add(await http.MultipartFile.fromPath('user_image', _galleryImage!.path));
      } else {
        request.fields['image_mode'] = "stock_cartoon";
        request.fields['stock_image_url'] = _stockAvatars[0];
      }

      // Extended 5-minute timeout for multi-scene rendering
      final streamedResponse = await request.send().timeout(const Duration(minutes: 5));
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        final tempDir = Directory.systemTemp;
        final file = File("${tempDir.path}/video_${DateTime.now().millisecondsSinceEpoch}.mp4");
        await file.writeAsBytes(response.bodyBytes);

        _videoPlayerController = VideoPlayerController.file(file);
        await _videoPlayerController!.initialize();
        _videoPlayerController!.setLooping(true);
        _videoPlayerController!.play();

        setState(() {
          _generatedVideoFile = file;
          _isLoading = false;
          _statusMsg = "Video generated successfully!";
        });
      } else {
        setState(() {
          _isLoading = false;
          _statusMsg = "Server error: ${response.statusCode}\n${response.body}";
        });
      }
    } catch (e) {
      setState(() {
        _isLoading = false;
        _statusMsg = "Generation failed: $e";
      });
    }
  }

  Future<void> _saveToDownloads() async {
    if (_generatedVideoFile == null) return;
    try {
      final extDir = Directory('/storage/emulated/0/Download');
      if (!await extDir.exists()) {
        await extDir.create(recursive: true);
      }
      final savePath = "${extDir.path}/ai_video_${DateTime.now().millisecondsSinceEpoch}.mp4";
      await _generatedVideoFile!.copy(savePath);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text("Saved to Downloads: $savePath")),
      );
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text("Download error: $e")),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("AI Video Generator"),
        backgroundColor: Colors.deepPurple,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text("Server URL", style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            TextField(
              controller: _urlController,
              decoration: const InputDecoration(
                border: OutlineInputBorder(),
                isDense: true,
              ),
            ),
            const Divider(height: 28),

            const Text("1. Select Format", style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: ChoiceChip(
                    label: const Center(child: Text("9:16 (Vertical)")),
                    selected: _aspectRatio == "9:16",
                    onSelected: (val) => setState(() => _aspectRatio = "9:16"),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ChoiceChip(
                    label: const Center(child: Text("16:9 (Landscape)")),
                    selected: _aspectRatio == "16:9",
                    onSelected: (val) => setState(() => _aspectRatio = "16:9"),
                  ),
                ),
              ],
            ),
            const Divider(height: 28),

            const Text("2. Voice & Script", style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            DropdownButtonFormField<String>(
              value: _selectedVoice,
              isExpanded: true,
              items: _voices.entries
                  .map((e) => DropdownMenuItem(value: e.value, child: Text(e.key)))
                  .toList(),
              onChanged: (val) => setState(() => _selectedVoice = val!),
              decoration: const InputDecoration(border: OutlineInputBorder(), isDense: true),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _scriptController,
              maxLines: 4,
              decoration: const InputDecoration(
                hintText: "Enter your story or ad script (Tamil / English)...",
                border: OutlineInputBorder(),
              ),
            ),
            const Divider(height: 28),

            const Text("3. Avatar Source", style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: "Cartoons", label: Text("Cartoons")),
                ButtonSegment(value: "Gallery", label: Text("Gallery")),
              ],
              selected: {_avatarSource},
              onSelectionChanged: (newSet) => setState(() => _avatarSource = newSet.first),
            ),
            const SizedBox(height: 12),

            if (_avatarSource == "Cartoons")
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: List.generate(_stockAvatars.length, (index) {
                  return GestureDetector(
                    onTap: () => setState(() => _selectedCartoonIndex = index),
                    child: Container(
                      padding: const EdgeInsets.all(4),
                      decoration: BoxDecoration(
                        border: Border.all(
                          color: _selectedCartoonIndex == index ? Colors.deepPurple : Colors.grey,
                          width: 3,
                        ),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Image.network(_stockAvatars[index], width: 70, height: 70, fit: BoxFit.cover),
                    ),
                  );
                }),
              )
            else
              Column(
                children: [
                  ElevatedButton.icon(
                    onPressed: _pickGalleryImage,
                    icon: const Icon(Icons.image),
                    label: const Text("Select Face Photo From Gallery"),
                  ),
                  if (_galleryImage != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 8.0),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: Image.file(_galleryImage!, height: 100),
                      ),
                    )
                ],
              ),

            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: _isLoading ? null : _generateVideo,
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 14),
                backgroundColor: Colors.deepPurple,
                foregroundColor: Colors.white,
              ),
              child: _isLoading
                  ? const Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                        ),
                        SizedBox(width: 12),
                        Text("Creating Scenes & Rendering..."),
                      ],
                    )
                  : const Text("Generate Video", style: TextStyle(fontSize: 16)),
            ),

            if (_statusMsg.isNotEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12.0),
                child: Text(
                  _statusMsg,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                  textAlign: TextAlign.center,
                ),
              ),

            // Video Preview, Download & Reset Controls
            if (_videoPlayerController != null && _videoPlayerController!.value.isInitialized) ...[
              const Divider(height: 32),
              AspectRatio(
                aspectRatio: _videoPlayerController!.value.aspectRatio,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: VideoPlayer(_videoPlayerController!),
                ),
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: ElevatedButton.icon(
                      onPressed: _saveToDownloads,
                      icon: const Icon(Icons.download),
                      label: const Text("Download"),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.green,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 12),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: _resetForNextVideo,
                      icon: const Icon(Icons.add),
                      label: const Text("Create Another"),
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 12),
                      ),
                    ),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 36),
          ],
        ),
      ),
    );
  }
}
