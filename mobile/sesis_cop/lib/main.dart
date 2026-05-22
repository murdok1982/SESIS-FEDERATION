import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:hydrated_bloc/hydrated_bloc.dart';
import 'package:path_provider/path_provider.dart';
import 'core/theme/app_theme.dart';
import 'features/auth/screens/login_screen.dart';
import 'features/dashboard/screens/cop_screen.dart';
import 'features/intel/screens/intel_feed_screen.dart';
import 'features/c2/screens/mission_screen.dart';
import 'features/agents/screens/agents_screen.dart';
import 'features/satellite/screens/satellite_screen.dart';
import 'features/auth/screens/duress_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final storage = await HydratedStorage.build(
    storageDirectory: await getTemporaryDirectory(),
  );
  HydratedBlocOverrides.runZoned(
    () => runApp(const SesisCopApp()),
    storage: storage,
  );
}

class SesisCopApp extends StatelessWidget {
  const SesisCopApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SESIS-COP',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.militaryDark,
      initialRoute: '/login',
      onGenerateRoute: _onGenerateRoute,
    );
  }

  Route<dynamic>? _onGenerateRoute(RouteSettings settings) {
    switch (settings.name) {
      case '/login':
        return MaterialPageRoute(builder: (_) => const LoginScreen());
      case '/duress':
        return MaterialPageRoute(builder: (_) => const DuressScreen());
      case '/cop':
        return MaterialPageRoute(builder: (_) => const CopScreen());
      case '/intel':
        return MaterialPageRoute(builder: (_) => const IntelFeedScreen());
      case '/mission':
        return MaterialPageRoute(builder: (_) => const MissionScreen());
      case '/agents':
        return MaterialPageRoute(builder: (_) => const AgentsScreen());
      case '/satellite':
        return MaterialPageRoute(builder: (_) => const SatelliteScreen());
      default:
        return MaterialPageRoute(builder: (_) => const LoginScreen());
    }
  }
}
