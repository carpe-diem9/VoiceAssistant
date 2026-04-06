// 数据模型定义

class User {
  final int id;
  final String username;
  final String createdAt;

  User({required this.id, required this.username, required this.createdAt});

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'],
      username: json['username'],
      createdAt: json['created_at'] ?? '',
    );
  }
}

class AuthResponse {
  final String accessToken;
  final String tokenType;
  final User user;

  AuthResponse({required this.accessToken, required this.tokenType, required this.user});

  factory AuthResponse.fromJson(Map<String, dynamic> json) {
    return AuthResponse(
      accessToken: json['access_token'],
      tokenType: json['token_type'] ?? 'bearer',
      user: User.fromJson(json['user']),
    );
  }
}

class Session {
  final int id;
  final int userId;
  final String title;
  final String createdAt;
  final String updatedAt;

  Session({
    required this.id,
    required this.userId,
    required this.title,
    required this.createdAt,
    required this.updatedAt,
  });

  factory Session.fromJson(Map<String, dynamic> json) {
    return Session(
      id: json['id'],
      userId: json['user_id'],
      title: json['title'] ?? '新对话',
      createdAt: json['created_at'] ?? '',
      updatedAt: json['updated_at'] ?? '',
    );
  }
}

class Message {
  final int? id;
  final int? sessionId;
  final String role;
  String content;
  final String? audioUrl;
  final String? createdAt;
  bool isStreaming;

  Message({
    this.id,
    this.sessionId,
    required this.role,
    required this.content,
    this.audioUrl,
    this.createdAt,
    this.isStreaming = false,
  });

  factory Message.fromJson(Map<String, dynamic> json) {
    return Message(
      id: json['id'],
      sessionId: json['session_id'],
      role: json['role'],
      content: json['content'] ?? '',
      audioUrl: json['audio_url'],
      createdAt: json['created_at'],
    );
  }
}

class TTSSettings {
  String voice;
  double speed;
  double pitch;
  int volume;
  List<String> availableVoices;

  TTSSettings({
    this.voice = 'Cherry',
    this.speed = 1.0,
    this.pitch = 1.0,
    this.volume = 50,
    this.availableVoices = const [],
  });

  factory TTSSettings.fromJson(Map<String, dynamic> json) {
    return TTSSettings(
      voice: json['voice'] ?? 'Cherry',
      speed: (json['speed'] ?? 1.0).toDouble(),
      pitch: (json['pitch'] ?? 1.0).toDouble(),
      volume: json['volume'] ?? 50,
      availableVoices: List<String>.from(json['available_voices'] ?? []),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'voice': voice,
      'speed': speed,
      'pitch': pitch,
      'volume': volume,
    };
  }
}
