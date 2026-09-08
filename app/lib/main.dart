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
        brightness: Brightness.light,
        scaffoldBackgroundColor: Colors.white,
        appBarTheme: const AppBarTheme(
          backgroundColor: Colors.white,
          foregroundColor: Colors.black,
          elevation: 0,
        ),
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.black).copyWith(
          primary: Colors.black,
          onPrimary: Colors.white,
          secondary: Colors.black,
        ),
        navigationBarTheme: NavigationBarThemeData(
          indicatorColor: Colors.black,
          iconTheme: WidgetStateProperty.resolveWith((s) =>
              IconThemeData(color: s.contains(WidgetState.selected) ? Colors.black : Colors.grey)),
          labelTextStyle: WidgetStateProperty.resolveWith((s) => TextStyle(
              fontSize: 12,
              fontWeight: s.contains(WidgetState.selected) ? FontWeight.bold : FontWeight.normal,
              color: s.contains(WidgetState.selected) ? Colors.black : Colors.grey)),
        ),
      ),
      home: const LoginPage(),
    );
  }
}
