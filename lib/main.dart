import 'dart:io';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:chewie/chewie.dart';
import 'package:video_player/video_player.dart';

void main() => runApp(const MaterialApp(home: VideoMakerApp()));

class VideoMakerApp extends StatefulWidget {
  const VideoMakerApp({Key? key}) : super(key: key);

  @override
  State<VideoMakerApp> createState() => _VideoMakerAppState();
}

class _VideoMakerAppState extends State<VideoMakerApp> {
  final String serverUrl = "https://weak-turtles-repair.loca.lt/generate";

  final TextEditingController _scriptController = TextEditingController();
  final TextEditingController _aiPromptController = TextEditingController();

  String _aspectRatio = "9:16";
  String _imageMode = "stock_cartoon";
  String _voice = "ta-IN-PallaviNeural";
  String? _selectedStockUrl;
  File? _galleryImage;
  File? _savedVideoFile;
  bool _isLoading = false;

  VideoPlayerController? _videoController;
  ChewieController? _chewieController;

  final List<String> _cartoons = [
    "https://cdn.pixabay.com/photo/2021/01/04/06/20/man-5886570_1280.png",
    "https://cdn.pixabay.com/photo/2016/08/20/05/38/avatar-1606916_1280.png",
    "https://cdn.pixabay.com/photo/2020/05/17/20/21/cat-5183427_1280.png"
  ];

  Future<void> _pickGalleryImage() async {
    final picked = await ImagePicker().pickImage(source: ImageSource.gallery);
    if (picked != null) {
      setState(() => _galleryImage = File(picked.path));
    }
  }

  Future<void> _generateVideo() async {
    setState(() => _isLoading = true);
    try {
      var request = http.MultipartRequest("POST", Uri.parse(serverUrl));
      request.headers['bypass-tunnel-reminder'] = 'true';

      request.fields['aspect_ratio'] = _aspectRatio;
      request.fields['image_mode'] = _imageMode;
      request.fields['voice'] = _voice;
      request.fields['script'] = _scriptController.text;

      if (_imageMode == "stock_cartoon" && _selectedStockUrl != null) {
        request.fields['stock_image_url'] = _selectedStockUrl!;
      } else if (_imageMode == "ai_image") {
        request.fields['ai_prompt'] = _aiPromptController.text;
      } else if (_imageMode == "upload" && _galleryImage != null) {
        request.files.add(await http.MultipartFile.fromPath('user_image', _galleryImage!.path));
      }

      final streamedResponse = await request.send();
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        final dir = await getTemporaryDirectory();
        final file = File('${dir.path}/generated_video.mp4');
        await file.writeAsBytes(response.bodyBytes);

        _savedVideoFile = file;

        _videoController?.dispose();
        _chewieController?.dispose();

        _videoController = VideoPlayerController.file(file);
        await _videoController!.initialize();

        setState(() {
          _chewieController = ChewieController(
            videoPlayerController: _videoController!,
            autoPlay: true,
            looping: true,
            aspectRatio: _aspectRatio == "9:16" ? 9 / 16 : 16 / 9,
          );
        });
      } else {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Error: ${response.body}")));
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("Failed: $e")));
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _downloadToPhone() async {
    if (_savedVideoFile == null) return;
    try {
      final downloadDir = Directory('/storage/emulated/0/Download');
      final fileName = 'AI_Video_${DateTime.now().millisecondsSinceEpoch}.mp4';
      final targetFile = File('${downloadDir.path}/$fileName');

      await _savedVideoFile!.copy(targetFile.path);

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text("Saved to Downloads: $fileName"),
          backgroundColor: Colors.green,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text("Save failed: $e")),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("AI Video Generator")),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text("1. Select Format", style: TextStyle(fontWeight: FontWeight.bold)),
            Row(
              children: [
                ChoiceChip(
                  label: const Text("9:16 (Vertical)"),
                  selected: _aspectRatio == "9:16",
                  onSelected: (_) => setState(() => _aspectRatio = "9:16"),
                ),
                const SizedBox(width: 8),
                ChoiceChip(
                  label: const Text("16:9 (Landscape)"),
                  selected: _aspectRatio == "16:9",
                  onSelected: (_) => setState(() => _aspectRatio = "16:9"),
                ),
              ],
            ),
            const Divider(height: 28),
            const Text("2. Voice & Script", style: TextStyle(fontWeight: FontWeight.bold)),
            DropdownButton<String>(
              value: _voice,
              isExpanded: true,
              items: const [
                DropdownMenuItem(value: "ta-IN-PallaviNeural", child: Text("Tamil (Female - Pallavi)")),
                DropdownMenuItem(value: "ta-IN-ValluvarNeural", child: Text("Tamil (Male - Valluvar)")),
                DropdownMenuItem(value: "en-IN-NeerjaNeural", child: Text("Indian English / Tanglish")),
              ],
              onChanged: (v) => setState(() => _voice = v!),
            ),
            TextField(
              controller: _scriptController,
              decoration: const InputDecoration(hintText: "Enter Tamil or English script..."),
              maxLines: 2,
            ),
            const Divider(height: 28),
            const Text("3. Avatar Source", style: TextStyle(fontWeight: FontWeight.bold)),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: "stock_cartoon", label: Text("Cartoons")),
                ButtonSegment(value: "ai_image", label: Text("AI Prompt")),
                ButtonSegment(value: "upload", label: Text("Gallery")),
              ],
              selected: {_imageMode},
              onSelectionChanged: (set) => setState(() => _imageMode = set.first),
            ),
            const SizedBox(height: 12),
            if (_imageMode == "stock_cartoon")
              SizedBox(
                height: 80,
                child: ListView.builder(
                  scrollDirection: Axis.horizontal,
                  itemCount: _cartoons.length,
                  itemBuilder: (ctx, i) => GestureDetector(
                    onTap: () => setState(() => _selectedStockUrl = _cartoons[i]),
                    child: Container(
                      margin: const EdgeInsets.only(right: 8),
                      decoration: BoxDecoration(
                        border: Border.all(
                          color: _selectedStockUrl == _cartoons[i] ? Colors.blue : Colors.grey,
                          width: 3,
                        ),
                      ),
                      child: Image.network(_cartoons[i], width: 70, fit: BoxFit.cover),
                    ),
                  ),
                ),
              )
            else if (_imageMode == "ai_image")
              TextField(
                controller: _aiPromptController,
                decoration: const InputDecoration(labelText: "AI Prompt (e.g. 3D cute cartoon boy)"),
              )
            else
              ElevatedButton.icon(
                onPressed: _pickGalleryImage,
                icon: const Icon(Icons.image),
                label: Text(_galleryImage == null ? "Pick Photo" : "Photo Selected"),
              ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              height: 48,
              child: ElevatedButton(
                onPressed: _isLoading ? null : _generateVideo,
                child: _isLoading
                    ? const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          CircularProgressIndicator(color: Colors.white),
                          SizedBox(width: 12),
                          Text("Generating video..."),
                        ],
                      )
                    : const Text("Generate AI Video"),
              ),
            ),
            const SizedBox(height: 20),
            if (_chewieController != null) ...[
              Center(
                child: AspectRatio(
                  aspectRatio: _aspectRatio == "9:16" ? 9 / 16 : 16 / 9,
                  child: Chewie(controller: _chewieController!),
                ),
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                height: 48,
                child: ElevatedButton.icon(
                  onPressed: _downloadToPhone,
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
                  icon: const Icon(Icons.download, color: Colors.white),
                  label: const Text(
                    "Download Video to Gallery / Storage",
                    style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                  ),
                ),
              ),
              const SizedBox(height: 30),
            ],
          ],
        ),
      ),
    );
  }
}
