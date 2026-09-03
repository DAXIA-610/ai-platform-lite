import 'package:flutter/material.dart';
import 'login_page.dart';

void main() => runApp(const MyApp());

class MyApp extends StatelessWidget {
  const MyApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI 社交',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0e0e0e),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF5b8def),
          brightness: Brightness.dark,
        ),
      ),
      home: const LoginPage(),
    );
  }
}
