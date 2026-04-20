import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { colors } from '../theme/dark';

import FaceScanScreen from '../screens/scan/FaceScanScreen';
import FaceScanResultsScreen from '../screens/scan/FaceScanResultsScreen';

const Stack = createNativeStackNavigator();

export default function ScanOnlyNavigator() {
    return (
        <Stack.Navigator
            initialRouteName="FaceScan"
            screenOptions={{
                headerShown: false,
                contentStyle: { backgroundColor: colors.background },
            }}
        >
            <Stack.Screen name="FaceScan" component={FaceScanScreen} />
            <Stack.Screen name="FaceScanResults" component={FaceScanResultsScreen} />
        </Stack.Navigator>
    );
}
