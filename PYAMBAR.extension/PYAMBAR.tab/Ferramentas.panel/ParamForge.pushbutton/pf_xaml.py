# -*- coding: utf-8 -*-
"""
ParamForge - XAML strings.
Icons: Segoe MDL2 Assets (built-in Windows 10/11) para botoes principais.
Unicode symbols para botoes pequenos (sem truncamento).
"""

XAML_MAIN = """
<Grid xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
      xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
    <Grid.Resources>
        <Style TargetType="TextBlock">
            <Setter Property="FontFamily" Value="Segoe UI"/>
            <Setter Property="Foreground" Value="#111827"/>
        </Style>
        <Style TargetType="Button">
            <Setter Property="Height" Value="28"/>
            <Setter Property="Margin" Value="2"/>
            <Setter Property="Background" Value="White"/>
            <Setter Property="BorderBrush" Value="#D1D5DB"/>
            <Setter Property="FontFamily" Value="Segoe UI"/>
            <Setter Property="FontSize" Value="11"/>
            <Setter Property="Cursor" Value="Hand"/>
        </Style>
        <Style x:Key="BtnPrimary" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
            <Setter Property="Background" Value="#7C3AED"/>
            <Setter Property="Foreground" Value="White"/>
            <Setter Property="BorderThickness" Value="0"/>
            <Setter Property="FontFamily" Value="Segoe UI Semibold"/>
        </Style>
        <Style x:Key="BtnSmall" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
            <Setter Property="Height" Value="24"/>
            <Setter Property="FontSize" Value="11"/>
            <Setter Property="Padding" Value="8,0"/>
        </Style>
        <Style x:Key="SmallIcon" TargetType="TextBlock">
            <Setter Property="FontFamily" Value="Segoe MDL2 Assets"/>
            <Setter Property="FontSize" Value="10"/>
            <Setter Property="VerticalAlignment" Value="Center"/>
            <Setter Property="Margin" Value="0,0,4,0"/>
        </Style>
        <Style x:Key="BtnMode" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
            <Setter Property="Height" Value="30"/>
            <Setter Property="FontSize" Value="11"/>
            <Setter Property="FontFamily" Value="Segoe UI Semibold"/>
            <Setter Property="Margin" Value="0"/>
        </Style>
        <Style x:Key="IconText" TargetType="TextBlock">
            <Setter Property="FontFamily" Value="Segoe MDL2 Assets"/>
            <Setter Property="FontSize" Value="12"/>
            <Setter Property="VerticalAlignment" Value="Center"/>
            <Setter Property="Margin" Value="0,0,5,0"/>
        </Style>
        <Style x:Key="SectionLabel" TargetType="TextBlock">
            <Setter Property="FontFamily" Value="Segoe UI Semibold"/>
            <Setter Property="FontWeight" Value="Bold"/>
            <Setter Property="FontSize" Value="11"/>
            <Setter Property="Foreground" Value="#7C3AED"/>
            <Setter Property="Margin" Value="0,0,0,6"/>
        </Style>
    </Grid.Resources>

    <Grid.RowDefinitions>
        <RowDefinition Height="Auto"/>
        <RowDefinition Height="*"/>
        <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>

    <!-- Header accent -->
    <Border Grid.Row="0" Background="#7C3AED" Height="4"/>

    <!-- Main content: 3 columns -->
    <Grid Grid.Row="1" Margin="10">
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="260"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="220"/>
        </Grid.ColumnDefinitions>

        <!-- ====== COL 1: CONFIG ====== -->
        <Grid Grid.Column="0">
            <Grid.RowDefinitions>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="*"/>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="*"/>
            </Grid.RowDefinitions>

            <!-- 3 Mode Buttons -->
            <Border Background="#F5F3FF" CornerRadius="4" Padding="4" Margin="0,0,0,6">
                <Grid>
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="*"/>
                        <ColumnDefinition Width="3"/>
                        <ColumnDefinition Width="*"/>
                        <ColumnDefinition Width="3"/>
                        <ColumnDefinition Width="*"/>
                    </Grid.ColumnDefinitions>
                    <Button x:Name="btnModoSelecao" Style="{StaticResource BtnMode}"
                            Content="Selecionar" ToolTip="Selecionar elementos no modelo"/>
                    <Button Grid.Column="2" x:Name="btnModoVista" Style="{StaticResource BtnMode}"
                            Content="Vista Ativa" ToolTip="Elementos da vista ativa"/>
                    <Button Grid.Column="4" x:Name="btnModoProjeto" Style="{StaticResource BtnMode}"
                            Content="Projeto" ToolTip="Todos os elementos do projeto"
                            Background="#7C3AED" Foreground="White" BorderThickness="0"/>
                </Grid>
            </Border>

            <!-- Categorias -->
            <Grid Grid.Row="1">
                <Grid.RowDefinitions>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="*"/>
                </Grid.RowDefinitions>
                <TextBlock Text="Categorias (Ctrl/Shift)" FontWeight="Bold" Margin="0,0,0,3" FontSize="11"/>
                <WrapPanel Grid.Row="1" Margin="0,0,0,3">
                    <CheckBox x:Name="chkDiscArch" Content="Arch" FontSize="10" Margin="0,0,6,2" IsChecked="True"/>
                    <CheckBox x:Name="chkDiscStruct" Content="Struct" FontSize="10" Margin="0,0,6,2" IsChecked="True"/>
                    <CheckBox x:Name="chkDiscMech" Content="Mech" FontSize="10" Margin="0,0,6,2" IsChecked="True"/>
                    <CheckBox x:Name="chkDiscElec" Content="Elec" FontSize="10" Margin="0,0,6,2" IsChecked="True"/>
                    <CheckBox x:Name="chkDiscPipe" Content="Piping" FontSize="10" Margin="0,0,0,2" IsChecked="True"/>
                </WrapPanel>
                <TextBox x:Name="txtCatSearch" Grid.Row="2" Height="22" Padding="2"
                         Text="Buscar categoria..." Foreground="Gray" Margin="0,0,0,3" FontSize="11"/>
                <Border Grid.Row="3" BorderBrush="#E5E7EB" BorderThickness="1">
                    <ListBox x:Name="lbCategories" SelectionMode="Extended" BorderThickness="0" FontSize="11">
                        <ListBox.ItemTemplate>
                            <DataTemplate>
                                <StackPanel Orientation="Horizontal">
                                    <CheckBox IsChecked="{Binding IsSelected, RelativeSource={RelativeSource AncestorType=ListBoxItem}, Mode=TwoWay}" Margin="0,0,4,0" VerticalAlignment="Center"/>
                                    <TextBlock Text="{Binding Name}" VerticalAlignment="Center"/>
                                </StackPanel>
                            </DataTemplate>
                        </ListBox.ItemTemplate>
                    </ListBox>
                </Border>
            </Grid>

            <!-- Parametros -->
            <Grid Grid.Row="3">
                <Grid.RowDefinitions>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="*"/>
                </Grid.RowDefinitions>
                <TextBlock Text="Parametros (Ctrl/Shift)" FontWeight="Bold" Margin="0,6,0,3" FontSize="11"/>
                <TextBox x:Name="txtSearch" Grid.Row="1" Height="22" Padding="2"
                         Text="Buscar..." Foreground="Gray" Margin="0,0,0,3" FontSize="11"/>
                <Border Grid.Row="2" BorderBrush="#E5E7EB" BorderThickness="1">
                    <ListBox x:Name="lbParameters" SelectionMode="Extended" BorderThickness="0" FontSize="11">
                        <ListBox.ItemTemplate>
                            <DataTemplate>
                                <StackPanel Orientation="Horizontal">
                                    <CheckBox IsChecked="{Binding IsSelected, RelativeSource={RelativeSource AncestorType=ListBoxItem}, Mode=TwoWay}" Margin="0,0,4,0" VerticalAlignment="Center"/>
                                    <TextBlock Text="{Binding}" VerticalAlignment="Center"/>
                                </StackPanel>
                            </DataTemplate>
                        </ListBox.ItemTemplate>
                    </ListBox>
                </Border>
            </Grid>
        </Grid>

        <!-- ====== COL 2: VALORES ====== -->
        <Grid Grid.Column="2">
            <Grid.RowDefinitions>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="*"/>
                <RowDefinition Height="Auto"/>
            </Grid.RowDefinitions>

            <!-- Header -->
            <StackPanel>
                <TextBlock Text="Valores" FontWeight="Bold" Margin="0,0,0,3" FontSize="11"/>
                <StackPanel Orientation="Horizontal" Margin="0,0,0,3">
                    <Button x:Name="btnSelectAll" Style="{StaticResource BtnSmall}">
                        <StackPanel Orientation="Horizontal">
                            <TextBlock Style="{StaticResource SmallIcon}" Text="&#xE73E;"/>
                            <TextBlock Text="Todos" VerticalAlignment="Center" FontSize="11"/>
                        </StackPanel>
                    </Button>
                    <Button x:Name="btnDeselectAll" Style="{StaticResource BtnSmall}">
                        <StackPanel Orientation="Horizontal">
                            <TextBlock Style="{StaticResource SmallIcon}" Text="&#xE711;"/>
                            <TextBlock Text="Nenhum" VerticalAlignment="Center" FontSize="11"/>
                        </StackPanel>
                    </Button>
                    <Button x:Name="btnRandom" Style="{StaticResource BtnSmall}"
                            ToolTip="Gerar cores aleatorias">
                        <StackPanel Orientation="Horizontal">
                            <TextBlock Style="{StaticResource SmallIcon}" Text="&#xE790;"/>
                            <TextBlock Text="Cores" VerticalAlignment="Center" FontSize="11"/>
                        </StackPanel>
                    </Button>
                    <Button x:Name="btnGradient" Style="{StaticResource BtnSmall}"
                            ToolTip="Gradiente de cores">
                        <StackPanel Orientation="Horizontal">
                            <TextBlock Style="{StaticResource SmallIcon}" Text="&#xE76B;"/>
                            <TextBlock Text="Gradiente" VerticalAlignment="Center" FontSize="11"/>
                        </StackPanel>
                    </Button>
                </StackPanel>
            </StackPanel>

            <!-- Values ListView -->
            <Border Grid.Row="1" BorderBrush="#E5E7EB" BorderThickness="1" Background="White">
                <ListView x:Name="lvValues" BorderThickness="0" FontSize="11">
                    <ListView.View>
                        <GridView>
                            <GridViewColumn Header="" Width="28">
                                <GridViewColumn.CellTemplate>
                                    <DataTemplate>
                                        <CheckBox IsChecked="{Binding IsChecked}" HorizontalAlignment="Center"/>
                                    </DataTemplate>
                                </GridViewColumn.CellTemplate>
                            </GridViewColumn>
                            <GridViewColumn Header="" Width="38">
                                <GridViewColumn.CellTemplate>
                                    <DataTemplate>
                                        <Border Width="26" Height="15" Background="{Binding ColorBrush}"
                                                BorderBrush="#9CA3AF" BorderThickness="1" CornerRadius="2"
                                                Cursor="Hand" ToolTip="Duplo-clique para editar cor"/>
                                    </DataTemplate>
                                </GridViewColumn.CellTemplate>
                            </GridViewColumn>
                            <GridViewColumn Header="Valor" Width="180" DisplayMemberBinding="{Binding Value}"/>
                            <GridViewColumn Header="Qtd" Width="40" DisplayMemberBinding="{Binding Count}"/>
                        </GridView>
                    </ListView.View>
                </ListView>
            </Border>

            <!-- Footer: preset + preview -->
            <DockPanel Grid.Row="2" Margin="0,4,0,0" LastChildFill="False">
                <StackPanel DockPanel.Dock="Left" Orientation="Horizontal">
                    <Button x:Name="btnSavePreset" Style="{StaticResource BtnSmall}"
                            ToolTip="Salvar preset de cores">
                        <StackPanel Orientation="Horizontal">
                            <TextBlock Style="{StaticResource SmallIcon}" Text="&#xE74E;"/>
                            <TextBlock Text="Salvar" VerticalAlignment="Center" FontSize="11"/>
                        </StackPanel>
                    </Button>
                    <Button x:Name="btnLoadPreset" Style="{StaticResource BtnSmall}"
                            ToolTip="Carregar preset de cores">
                        <StackPanel Orientation="Horizontal">
                            <TextBlock Style="{StaticResource SmallIcon}" Text="&#xE8E5;"/>
                            <TextBlock Text="Carregar" VerticalAlignment="Center" FontSize="11"/>
                        </StackPanel>
                    </Button>
                    <Button x:Name="btnReset" Style="{StaticResource BtnSmall}"
                            ToolTip="Resetar cores">
                        <StackPanel Orientation="Horizontal">
                            <TextBlock Style="{StaticResource SmallIcon}" Text="&#xE72C;" Foreground="#EF4444"/>
                            <TextBlock Text="Reset" VerticalAlignment="Center" FontSize="11" Foreground="#EF4444"/>
                        </StackPanel>
                    </Button>
                </StackPanel>
                <StackPanel DockPanel.Dock="Right" Orientation="Horizontal">
                    <Button x:Name="btnPreviewSel" Style="{StaticResource BtnSmall}"
                            ToolTip="Selecionar elementos marcados">
                        <StackPanel Orientation="Horizontal">
                            <TextBlock Style="{StaticResource SmallIcon}" Text="&#xEF20;"/>
                            <TextBlock Text="Selecionar" VerticalAlignment="Center" FontSize="11"/>
                        </StackPanel>
                    </Button>
                    <Button x:Name="btnPreviewIso" Style="{StaticResource BtnSmall}"
                            ToolTip="Isolar elementos marcados">
                        <StackPanel Orientation="Horizontal">
                            <TextBlock Style="{StaticResource SmallIcon}" Text="&#xE71D;"/>
                            <TextBlock Text="Isolar" VerticalAlignment="Center" FontSize="11"/>
                        </StackPanel>
                    </Button>
                    <Button x:Name="btnPreview3D" Style="{StaticResource BtnSmall}"
                            ToolTip="Isolar em vista 3D">
                        <StackPanel Orientation="Horizontal">
                            <TextBlock Style="{StaticResource SmallIcon}" Text="&#xEC07;"/>
                            <TextBlock Text="3D" VerticalAlignment="Center" FontSize="11"/>
                        </StackPanel>
                    </Button>
                </StackPanel>
            </DockPanel>
        </Grid>

        <!-- ====== COL 3: ACOES ====== -->
        <ScrollViewer Grid.Column="4" VerticalScrollBarVisibility="Auto">
            <StackPanel Margin="4,0,0,0">
                <!-- VISUALIZAR -->
                <TextBlock Text="VISUALIZAR" Style="{StaticResource SectionLabel}"/>

                <CheckBox x:Name="chkAllViews" Content="Todas as vistas" Margin="0,0,0,6" FontSize="11"
                          ToolTip="Aplicar em todas as vistas do projeto"/>

                <Button x:Name="btnApply" Style="{StaticResource BtnPrimary}"
                        Height="32" Margin="0,0,0,4">
                    <StackPanel Orientation="Horizontal">
                        <TextBlock Style="{StaticResource IconText}" Text="&#xE790;"
                                   FontSize="13" Foreground="White"/>
                        <TextBlock Text="APLICAR CORES" VerticalAlignment="Center"
                                   FontWeight="Bold" Foreground="White" FontFamily="Segoe UI Semibold"/>
                    </StackPanel>
                </Button>
                <Button x:Name="btnResetCores" Height="26" Margin="0,0,0,8">
                    <StackPanel Orientation="Horizontal">
                        <TextBlock Style="{StaticResource IconText}" Text="&#xE72C;"
                                   FontSize="11" Foreground="#EF4444"/>
                        <TextBlock Text="Resetar Cores" VerticalAlignment="Center" Foreground="#EF4444"/>
                    </StackPanel>
                </Button>

                <Button x:Name="btnFilters" Height="26" Margin="0,0,0,4">
                    <StackPanel Orientation="Horizontal">
                        <TextBlock Style="{StaticResource IconText}" Text="&#xE71C;" FontSize="11"/>
                        <TextBlock Text="Criar Filtros" VerticalAlignment="Center"/>
                    </StackPanel>
                </Button>
                <Button x:Name="btnLegend" Height="26" Margin="0,0,0,12">
                    <StackPanel Orientation="Horizontal">
                        <TextBlock Style="{StaticResource IconText}" Text="&#xE8FD;" FontSize="11"/>
                        <TextBlock Text="Criar Legenda..." VerticalAlignment="Center"/>
                    </StackPanel>
                </Button>

                <!-- SEPARADOR -->
                <Border Background="#E5E7EB" Height="1" Margin="0,0,0,10"/>

                <!-- DOCUMENTAR -->
                <TextBlock Text="DOCUMENTAR" Style="{StaticResource SectionLabel}"/>

                <!-- Templates dinamicos por categoria -->
                <StackPanel x:Name="pnlTemplates">
                    <!-- Preenchido dinamicamente -->
                </StackPanel>

                <CheckBox x:Name="chkVerTodos" Content="Ver todos schedules" Margin="0,4,0,6" FontSize="11"/>

                <TextBlock Text="Prefixo:" FontSize="11" Margin="0,0,0,2"/>
                <TextBox x:Name="txtPrefix" Height="22" FontSize="11" Margin="0,0,0,8"/>

                <Button x:Name="btnCreateSchedules" Style="{StaticResource BtnPrimary}"
                        Height="32">
                    <StackPanel Orientation="Horizontal">
                        <TextBlock Style="{StaticResource IconText}" Text="&#xE8A5;"
                                   FontSize="13" Foreground="White"/>
                        <TextBlock Text="CRIAR SCHEDULES" VerticalAlignment="Center"
                                   FontWeight="Bold" Foreground="White" FontFamily="Segoe UI Semibold"/>
                    </StackPanel>
                </Button>
            </StackPanel>
        </ScrollViewer>
    </Grid>

    <!-- Status bar -->
    <Border Grid.Row="2" Background="#F3F4F6" Padding="10,4">
        <TextBlock x:Name="txtStatus" Text="Pronto." FontSize="11" Foreground="#6B7280"/>
    </Border>
</Grid>
"""

XAML_LEGEND = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Configurar Legenda" Height="600" Width="550"
        WindowStartupLocation="CenterScreen" ResizeMode="NoResize">
    <Grid>
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <Border Grid.Row="0" Background="#7C3AED" Padding="15,10">
            <TextBlock Text="Configuracao da Legenda" FontSize="16" FontWeight="Bold" Foreground="White"/>
        </Border>

        <ScrollViewer Grid.Row="1" VerticalScrollBarVisibility="Auto">
            <StackPanel Margin="15">
                <GroupBox Header="Nome da Vista" Padding="10" Margin="0,0,0,10">
                    <TextBox x:Name="txtTitle" Text="Legenda de Cores" Height="28" FontSize="13"/>
                </GroupBox>

                <GroupBox Header="Dimensoes das Caixas" Padding="10" Margin="0,0,0,10">
                    <Grid>
                        <Grid.ColumnDefinitions>
                            <ColumnDefinition Width="*"/>
                            <ColumnDefinition Width="15"/>
                            <ColumnDefinition Width="*"/>
                        </Grid.ColumnDefinitions>
                        <StackPanel>
                            <TextBlock Text="Largura:" Margin="0,0,0,3"/>
                            <ComboBox x:Name="cmbWidth" Height="25" SelectedIndex="4">
                                <ComboBoxItem Content="1/4&quot;"/>
                                <ComboBoxItem Content="1/2&quot;"/>
                                <ComboBoxItem Content="3/4&quot;"/>
                                <ComboBoxItem Content="7/8&quot;"/>
                                <ComboBoxItem Content="1&quot;"/>
                                <ComboBoxItem Content="1-1/4&quot;"/>
                                <ComboBoxItem Content="1-1/2&quot;"/>
                                <ComboBoxItem Content="2&quot;"/>
                            </ComboBox>
                        </StackPanel>
                        <StackPanel Grid.Column="2">
                            <TextBlock Text="Altura:" Margin="0,0,0,3"/>
                            <ComboBox x:Name="cmbHeight" Height="25" SelectedIndex="4">
                                <ComboBoxItem Content="1/4&quot;"/>
                                <ComboBoxItem Content="1/2&quot;"/>
                                <ComboBoxItem Content="3/4&quot;"/>
                                <ComboBoxItem Content="7/8&quot;"/>
                                <ComboBoxItem Content="1&quot;"/>
                                <ComboBoxItem Content="1-1/4&quot;"/>
                                <ComboBoxItem Content="1-1/2&quot;"/>
                                <ComboBoxItem Content="2&quot;"/>
                            </ComboBox>
                        </StackPanel>
                    </Grid>
                </GroupBox>

                <GroupBox Header="Espacamentos" Padding="10" Margin="0,0,0,10">
                    <StackPanel>
                        <Grid Margin="0,0,0,8">
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="*"/>
                                <ColumnDefinition Width="15"/>
                                <ColumnDefinition Width="*"/>
                            </Grid.ColumnDefinitions>
                            <StackPanel>
                                <TextBlock Text="Caixa - Texto:" Margin="0,0,0,3"/>
                                <ComboBox x:Name="cmbOffset" Height="25" SelectedIndex="4">
                                    <ComboBoxItem Content="1/8&quot;"/>
                                    <ComboBoxItem Content="1/4&quot;"/>
                                    <ComboBoxItem Content="3/8&quot;"/>
                                    <ComboBoxItem Content="1/2&quot;"/>
                                    <ComboBoxItem Content="1&quot;"/>
                                    <ComboBoxItem Content="1-1/2&quot;"/>
                                    <ComboBoxItem Content="2&quot;"/>
                                </ComboBox>
                            </StackPanel>
                            <StackPanel Grid.Column="2">
                                <TextBlock Text="Entre Linhas:" Margin="0,0,0,3"/>
                                <ComboBox x:Name="cmbSpacing" Height="25" SelectedIndex="4">
                                    <ComboBoxItem Content="1/8&quot;"/>
                                    <ComboBoxItem Content="1/4&quot;"/>
                                    <ComboBoxItem Content="3/8&quot;"/>
                                    <ComboBoxItem Content="1/2&quot;"/>
                                    <ComboBoxItem Content="1&quot;"/>
                                    <ComboBoxItem Content="1-1/2&quot;"/>
                                    <ComboBoxItem Content="2&quot;"/>
                                </ComboBox>
                            </StackPanel>
                        </Grid>
                        <TextBlock Text="Titulo - Primeira Linha:" Margin="0,0,0,3"/>
                        <ComboBox x:Name="cmbTitleSpacing" Height="25" SelectedIndex="5">
                            <ComboBoxItem Content="1/2&quot;"/>
                            <ComboBoxItem Content="3/4&quot;"/>
                            <ComboBoxItem Content="1&quot;"/>
                            <ComboBoxItem Content="1-1/4&quot;"/>
                            <ComboBoxItem Content="1-1/2&quot;"/>
                            <ComboBoxItem Content="2&quot;"/>
                        </ComboBox>
                    </StackPanel>
                </GroupBox>

                <GroupBox Header="Borda Externa" Padding="10" Margin="0,0,0,10">
                    <StackPanel>
                        <TextBlock Text="Margem da borda:" Margin="0,0,0,3"/>
                        <ComboBox x:Name="cmbBorderOffset" Height="25" SelectedIndex="4" Margin="0,0,0,8">
                            <ComboBoxItem Content="1/4&quot;"/>
                            <ComboBoxItem Content="1/2&quot;"/>
                            <ComboBoxItem Content="3/4&quot;"/>
                            <ComboBoxItem Content="7/8&quot;"/>
                            <ComboBoxItem Content="1&quot;"/>
                            <ComboBoxItem Content="1-1/4&quot;"/>
                            <ComboBoxItem Content="1-1/2&quot;"/>
                            <ComboBoxItem Content="2&quot;"/>
                        </ComboBox>
                        <TextBlock Text="Margem inferior:" Margin="0,0,0,3"/>
                        <ComboBox x:Name="cmbBorderBottom" Height="25" SelectedIndex="5">
                            <ComboBoxItem Content="1/4&quot;"/>
                            <ComboBoxItem Content="1/2&quot;"/>
                            <ComboBoxItem Content="3/4&quot;"/>
                            <ComboBoxItem Content="7/8&quot;"/>
                            <ComboBoxItem Content="1&quot;"/>
                            <ComboBoxItem Content="1-1/4&quot;"/>
                            <ComboBoxItem Content="1-1/2&quot;"/>
                            <ComboBoxItem Content="2&quot;"/>
                        </ComboBox>
                    </StackPanel>
                </GroupBox>

                <GroupBox Header="Ordenacao" Padding="10" Margin="0,0,0,10">
                    <StackPanel>
                        <RadioButton x:Name="rbOrderOriginal" Content="Ordem Original" IsChecked="True" Margin="0,0,0,5"/>
                        <RadioButton x:Name="rbOrderAlpha" Content="Ordem Alfabetica" Margin="0,0,0,5"/>
                        <RadioButton x:Name="rbOrderCount" Content="Ordem por Quantidade" Margin="0,0,0,8"/>
                        <CheckBox x:Name="chkShowCount" Content="Mostrar quantidade apos o valor" IsChecked="True"/>
                    </StackPanel>
                </GroupBox>
            </StackPanel>
        </ScrollViewer>

        <Border Grid.Row="2" Background="#F3F4F6" Padding="15,10" BorderBrush="#E5E7EB" BorderThickness="0,1,0,0">
            <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
                <Button x:Name="btnCancel" Content="Cancelar" Width="100" Height="32" Margin="0,0,10,0"/>
                <Button x:Name="btnCreate" Content="Criar Legenda" Width="130" Height="32"
                        Background="#7C3AED" Foreground="White" FontWeight="Bold" BorderThickness="0"/>
            </StackPanel>
        </Border>
    </Grid>
</Window>
"""

XAML_CONFIRM = """
<Grid xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
      xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
    <Grid.RowDefinitions>
        <RowDefinition Height="Auto"/>
        <RowDefinition Height="Auto"/>
        <RowDefinition Height="*"/>
        <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>

    <Border Grid.Row="0" Background="#7C3AED" Padding="16,10">
        <StackPanel>
            <TextBlock x:Name="lblHeader" Text="Confirmar criacao de schedules"
                       Foreground="White" FontSize="14" FontWeight="Bold" FontFamily="Segoe UI"/>
            <TextBlock Text="Desmarque itens que nao deseja criar. Edite nomes e Schedule Category."
                       Foreground="#DDD6FE" FontSize="11" FontFamily="Segoe UI" Margin="0,2,0,0"/>
        </StackPanel>
    </Border>

    <!-- Column headers -->
    <Border Grid.Row="1" Background="#F5F3FF" Padding="8,6" BorderBrush="#E5E7EB" BorderThickness="0,0,0,1">
        <Grid>
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="28"/>
                <ColumnDefinition Width="120"/>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="160"/>
            </Grid.ColumnDefinitions>
            <TextBlock Grid.Column="1" Text="Valor" FontSize="10" Foreground="#6B7280"
                       FontFamily="Segoe UI" FontWeight="Bold" VerticalAlignment="Center"/>
            <TextBlock Grid.Column="2" Text="Nome do Schedule" FontSize="10" Foreground="#6B7280"
                       FontFamily="Segoe UI" FontWeight="Bold" VerticalAlignment="Center" Margin="4,0"/>
            <TextBlock Grid.Column="3" Text="Schedule Category" FontSize="10" Foreground="#6B7280"
                       FontFamily="Segoe UI" FontWeight="Bold" VerticalAlignment="Center" Margin="4,0"/>
        </Grid>
    </Border>

    <ScrollViewer Grid.Row="2" VerticalScrollBarVisibility="Auto">
        <ItemsControl x:Name="itemsList">
            <ItemsControl.ItemTemplate>
                <DataTemplate>
                    <Border BorderBrush="#F3F4F6" BorderThickness="0,0,0,1" Padding="8,3">
                        <Grid>
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="28"/>
                                <ColumnDefinition Width="120"/>
                                <ColumnDefinition Width="*"/>
                                <ColumnDefinition Width="160"/>
                            </Grid.ColumnDefinitions>
                            <CheckBox IsChecked="{Binding IsChecked, Mode=TwoWay}"
                                      HorizontalAlignment="Center" VerticalAlignment="Center"/>
                            <TextBlock Grid.Column="1" Text="{Binding FiltroDisplay}" FontSize="10"
                                       Foreground="#374151" VerticalAlignment="Center"
                                       Margin="4,0" FontFamily="Segoe UI" TextTrimming="CharacterEllipsis"/>
                            <TextBox Grid.Column="2"
                                     Text="{Binding Nome, Mode=TwoWay, UpdateSourceTrigger=PropertyChanged}"
                                     FontSize="10" Height="24" Padding="4,2"
                                     BorderBrush="#D1D5DB" FontFamily="Segoe UI"
                                     VerticalContentAlignment="Center" Margin="2,0"/>
                            <TextBox Grid.Column="3"
                                     Text="{Binding ScheduleCategory, Mode=TwoWay, UpdateSourceTrigger=PropertyChanged}"
                                     FontSize="10" Height="24" Padding="4,2"
                                     BorderBrush="#D1D5DB" FontFamily="Segoe UI"
                                     VerticalContentAlignment="Center" Margin="2,0"/>
                        </Grid>
                    </Border>
                </DataTemplate>
            </ItemsControl.ItemTemplate>
        </ItemsControl>
    </ScrollViewer>

    <Border Grid.Row="3" Background="#F9FAFB" BorderBrush="#E5E7EB" BorderThickness="0,1,0,0" Padding="12,10">
        <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
            <Button x:Name="btnCancelar" Content="Cancelar" Width="90" Height="34"
                    Margin="0,0,8,0" FontFamily="Segoe UI" Cursor="Hand"/>
            <Button x:Name="btnConfirmar" Content="Criar Schedules" Width="160" Height="34"
                    Background="#7C3AED" Foreground="White" BorderThickness="0"
                    FontWeight="Bold" FontFamily="Segoe UI Semibold" Cursor="Hand"/>
        </StackPanel>
    </Border>
</Grid>
"""
