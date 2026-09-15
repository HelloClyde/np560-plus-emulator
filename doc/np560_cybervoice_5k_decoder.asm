; CyberVoice Player x86 evidence, NOT DMCU guest code.
; SHA256 e20d6097cc31c2cdc3f9c6961386c609fd8aa147c0c14145cb83c96e8d4ec7eb
; Original installer not executed. Member is internally CRC verified; outer ZIP is truncated.
; bit-reader-and-frame

/mnt/c/Users/ASUS/Documents/ChatGPT/np560/doc/sources/cybervoice-2000-20260907/member-16-00077c23.bin:     file format pei-i386


Disassembly of section .text:

004030ee <.text+0x20ee>:
  4030ee:	55                   	push   ebp
  4030ef:	8b ec                	mov    ebp,esp
  4030f1:	83 ec 0c             	sub    esp,0xc
  4030f4:	66 b8 08 00          	mov    ax,0x8
  4030f8:	53                   	push   ebx
  4030f9:	66 c7 45 fe 00 00    	mov    WORD PTR [ebp-0x2],0x0
  4030ff:	66 8b 55 0c          	mov    dx,WORD PTR [ebp+0xc]
  403103:	56                   	push   esi
  403104:	57                   	push   edi
  403105:	8b 75 18             	mov    esi,DWORD PTR [ebp+0x18]
  403108:	66 8b 1e             	mov    bx,WORD PTR [esi]
  40310b:	8b 4d 14             	mov    ecx,DWORD PTR [ebp+0x14]
  40310e:	66 2b c3             	sub    ax,bx
  403111:	66 89 45 fc          	mov    WORD PTR [ebp-0x4],ax
  403115:	66 3b d0             	cmp    dx,ax
  403118:	7f 4f                	jg     0x403169
  40311a:	0f bf 01             	movsx  eax,WORD PTR [ecx]
  40311d:	8b 7d 10             	mov    edi,DWORD PTR [ebp+0x10]
  403120:	8a cb                	mov    cl,bl
  403122:	8a 04 38             	mov    al,BYTE PTR [eax+edi*1]
  403125:	d2 e8                	shr    al,cl
  403127:	88 45 fe             	mov    BYTE PTR [ebp-0x2],al
  40312a:	8d 04 13             	lea    eax,[ebx+edx*1]
  40312d:	66 89 06             	mov    WORD PTR [esi],ax
  403130:	66 3d 08 00          	cmp    ax,0x8
  403134:	75 28                	jne    0x40315e
  403136:	66 c7 06 00 00       	mov    WORD PTR [esi],0x0
  40313b:	8b 4d 14             	mov    ecx,DWORD PTR [ebp+0x14]
  40313e:	66 ff 01             	inc    WORD PTR [ecx]
  403141:	b8 ff 00 00 00       	mov    eax,0xff
  403146:	b1 08                	mov    cl,0x8
  403148:	2a ca                	sub    cl,dl
  40314a:	d3 f8                	sar    eax,cl
  40314c:	8b 4d 08             	mov    ecx,DWORD PTR [ebp+0x8]
  40314f:	20 45 fe             	and    BYTE PTR [ebp-0x2],al
  403152:	66 8b 55 fe          	mov    dx,WORD PTR [ebp-0x2]
  403156:	66 89 11             	mov    WORD PTR [ecx],dx
  403159:	e9 07 01 00 00       	jmp    0x403265
  40315e:	7e e1                	jle    0x403141
  403160:	66 b8 ff ff          	mov    ax,0xffff
  403164:	e9 00 01 00 00       	jmp    0x403269
  403169:	66 8b 01             	mov    ax,WORD PTR [ecx]
  40316c:	8b 7d 10             	mov    edi,DWORD PTR [ebp+0x10]
  40316f:	c7 45 f8 ff 00 00 00 	mov    DWORD PTR [ebp-0x8],0xff
  403176:	8a cb                	mov    cl,bl
  403178:	d3 7d f8             	sar    DWORD PTR [ebp-0x8],cl
  40317b:	0f bf d8             	movsx  ebx,ax
  40317e:	66 2b 55 fc          	sub    dx,WORD PTR [ebp-0x4]
  403182:	8a 1c 3b             	mov    bl,BYTE PTR [ebx+edi*1]
  403185:	d2 eb                	shr    bl,cl
  403187:	22 5d f8             	and    bl,BYTE PTR [ebp-0x8]
  40318a:	8b 4d 14             	mov    ecx,DWORD PTR [ebp+0x14]
  40318d:	66 40                	inc    ax
  40318f:	66 89 01             	mov    WORD PTR [ecx],ax
  403192:	88 5d fe             	mov    BYTE PTR [ebp-0x2],bl
  403195:	0f bf d8             	movsx  ebx,ax
  403198:	8a 0c 3b             	mov    cl,BYTE PTR [ebx+edi*1]
  40319b:	8a d9                	mov    bl,cl
  40319d:	88 4d f4             	mov    BYTE PTR [ebp-0xc],cl
  4031a0:	8a 4d fc             	mov    cl,BYTE PTR [ebp-0x4]
  4031a3:	d2 e3                	shl    bl,cl
  4031a5:	88 5d fb             	mov    BYTE PTR [ebp-0x5],bl
  4031a8:	66 8b 1e             	mov    bx,WORD PTR [esi]
  4031ab:	66 3b d3             	cmp    dx,bx
  4031ae:	7f 24                	jg     0x4031d4
  4031b0:	66 8b cb             	mov    cx,bx
  4031b3:	b8 ff 00 00 00       	mov    eax,0xff
  4031b8:	66 89 16             	mov    WORD PTR [esi],dx
  4031bb:	2a ca                	sub    cl,dl
  4031bd:	d3 f8                	sar    eax,cl
  4031bf:	22 45 fb             	and    al,BYTE PTR [ebp-0x5]
  4031c2:	8b 4d 08             	mov    ecx,DWORD PTR [ebp+0x8]
  4031c5:	08 45 fe             	or     BYTE PTR [ebp-0x2],al
  4031c8:	66 8b 55 fe          	mov    dx,WORD PTR [ebp-0x2]
  4031cc:	66 89 11             	mov    WORD PTR [ecx],dx
  4031cf:	e9 91 00 00 00       	jmp    0x403265
  4031d4:	66 2b d3             	sub    dx,bx
  4031d7:	8a 4d fb             	mov    cl,BYTE PTR [ebp-0x5]
  4031da:	08 4d fe             	or     BYTE PTR [ebp-0x2],cl
  4031dd:	8a 4d f4             	mov    cl,BYTE PTR [ebp-0xc]
  4031e0:	88 4d f8             	mov    BYTE PTR [ebp-0x8],cl
  4031e3:	8a cb                	mov    cl,bl
  4031e5:	d2 6d f8             	shr    BYTE PTR [ebp-0x8],cl
  4031e8:	66 3b 55 fc          	cmp    dx,WORD PTR [ebp-0x4]
  4031ec:	8a 4d f8             	mov    cl,BYTE PTR [ebp-0x8]
  4031ef:	88 4d fb             	mov    BYTE PTR [ebp-0x5],cl
  4031f2:	7f 25                	jg     0x403219
  4031f4:	b8 ff 00 00 00       	mov    eax,0xff
  4031f9:	b1 08                	mov    cl,0x8
  4031fb:	2a ca                	sub    cl,dl
  4031fd:	d3 f8                	sar    eax,cl
  4031ff:	22 45 fb             	and    al,BYTE PTR [ebp-0x5]
  403202:	88 45 ff             	mov    BYTE PTR [ebp-0x1],al
  403205:	8d 04 13             	lea    eax,[ebx+edx*1]
  403208:	66 89 06             	mov    WORD PTR [esi],ax
  40320b:	66 3d 08 00          	cmp    ax,0x8
  40320f:	74 3f                	je     0x403250
  403211:	7e 48                	jle    0x40325b
  403213:	66 b8 ff ff          	mov    ax,0xffff
  403217:	eb 50                	jmp    0x403269
  403219:	66 40                	inc    ax
  40321b:	8b 4d 14             	mov    ecx,DWORD PTR [ebp+0x14]
  40321e:	66 89 01             	mov    WORD PTR [ecx],ax
  403221:	bb ff 00 00 00       	mov    ebx,0xff
  403226:	66 2b 55 fc          	sub    dx,WORD PTR [ebp-0x4]
  40322a:	8b 7d 10             	mov    edi,DWORD PTR [ebp+0x10]
  40322d:	0f bf c0             	movsx  eax,ax
  403230:	8a 4d fc             	mov    cl,BYTE PTR [ebp-0x4]
  403233:	8a 04 38             	mov    al,BYTE PTR [eax+edi*1]
  403236:	d2 e0                	shl    al,cl
  403238:	66 8b 0e             	mov    cx,WORD PTR [esi]
  40323b:	66 89 16             	mov    WORD PTR [esi],dx
  40323e:	2a ca                	sub    cl,dl
  403240:	d3 fb                	sar    ebx,cl
  403242:	22 c3                	and    al,bl
  403244:	0a 45 fb             	or     al,BYTE PTR [ebp-0x5]
  403247:	66 83 fa 08          	cmp    dx,0x8
  40324b:	88 45 ff             	mov    BYTE PTR [ebp-0x1],al
  40324e:	75 0b                	jne    0x40325b
  403250:	66 c7 06 00 00       	mov    WORD PTR [esi],0x0
  403255:	8b 4d 14             	mov    ecx,DWORD PTR [ebp+0x14]
  403258:	66 ff 01             	inc    WORD PTR [ecx]
  40325b:	66 8b 45 fe          	mov    ax,WORD PTR [ebp-0x2]
  40325f:	8b 4d 08             	mov    ecx,DWORD PTR [ebp+0x8]
  403262:	66 89 01             	mov    WORD PTR [ecx],ax
  403265:	66 b8 01 00          	mov    ax,0x1
  403269:	5f                   	pop    edi
  40326a:	5e                   	pop    esi
  40326b:	5b                   	pop    ebx
  40326c:	8b e5                	mov    esp,ebp
  40326e:	5d                   	pop    ebp
  40326f:	c3                   	ret    
  403270:	55                   	push   ebp
  403271:	8b 44 24 28          	mov    eax,DWORD PTR [esp+0x28]
  403275:	66 8b 00             	mov    ax,WORD PTR [eax]
  403278:	8b ec                	mov    ebp,esp
  40327a:	83 ec 04             	sub    esp,0x4
  40327d:	66 89 45 fc          	mov    WORD PTR [ebp-0x4],ax
  403281:	53                   	push   ebx
  403282:	66 3d 01 00          	cmp    ax,0x1
  403286:	56                   	push   esi
  403287:	57                   	push   edi
  403288:	75 09                	jne    0x403293
  40328a:	66 8b 5d 18          	mov    bx,WORD PTR [ebp+0x18]
  40328e:	8b 7d 10             	mov    edi,DWORD PTR [ebp+0x10]
  403291:	eb 07                	jmp    0x40329a
  403293:	66 8b 5d 1c          	mov    bx,WORD PTR [ebp+0x1c]
  403297:	8b 7d 14             	mov    edi,DWORD PTR [ebp+0x14]
  40329a:	8b 75 20             	mov    esi,DWORD PTR [ebp+0x20]
  40329d:	0f bf cb             	movsx  ecx,bx
  4032a0:	66 8b 06             	mov    ax,WORD PTR [esi]
  4032a3:	0f bf d0             	movsx  edx,ax
  4032a6:	2b ca                	sub    ecx,edx
  4032a8:	0f bf 55 0c          	movsx  edx,WORD PTR [ebp+0xc]
  4032ac:	3b ca                	cmp    ecx,edx
  4032ae:	7e 18                	jle    0x4032c8
  4032b0:	ff 75 24             	push   DWORD PTR [ebp+0x24]
  4032b3:	56                   	push   esi
  4032b4:	57                   	push   edi
  4032b5:	ff 75 0c             	push   DWORD PTR [ebp+0xc]
  4032b8:	ff 75 08             	push   DWORD PTR [ebp+0x8]
  4032bb:	e8 2e fe ff ff       	call   0x4030ee
  4032c0:	83 c4 14             	add    esp,0x14
  4032c3:	e9 b3 00 00 00       	jmp    0x40337b
  4032c8:	66 2b d8             	sub    bx,ax
  4032cb:	8b 4d 24             	mov    ecx,DWORD PTR [ebp+0x24]
  4032ce:	66 c1 e3 03          	shl    bx,0x3
  4032d2:	66 2b 19             	sub    bx,WORD PTR [ecx]
  4032d5:	66 39 5d 0c          	cmp    WORD PTR [ebp+0xc],bx
  4032d9:	7f 30                	jg     0x40330b
  4032db:	51                   	push   ecx
  4032dc:	56                   	push   esi
  4032dd:	57                   	push   edi
  4032de:	ff 75 0c             	push   DWORD PTR [ebp+0xc]
  4032e1:	ff 75 08             	push   DWORD PTR [ebp+0x8]
  4032e4:	e8 05 fe ff ff       	call   0x4030ee
  4032e9:	83 c4 14             	add    esp,0x14
  4032ec:	66 39 5d 0c          	cmp    WORD PTR [ebp+0xc],bx
  4032f0:	0f 85 85 00 00 00    	jne    0x40337b
  4032f6:	8b 45 28             	mov    eax,DWORD PTR [ebp+0x28]
  4032f9:	8b 4d 24             	mov    ecx,DWORD PTR [ebp+0x24]
  4032fc:	66 c7 00 02 00       	mov    WORD PTR [eax],0x2
  403301:	33 c0                	xor    eax,eax
  403303:	66 89 01             	mov    WORD PTR [ecx],ax
  403306:	66 89 06             	mov    WORD PTR [esi],ax
  403309:	eb 70                	jmp    0x40337b
  40330b:	66 83 7d fc 02       	cmp    WORD PTR [ebp-0x4],0x2
  403310:	75 1d                	jne    0x40332f
  403312:	66 39 5d 0c          	cmp    WORD PTR [ebp+0xc],bx
  403316:	7e 17                	jle    0x40332f
  403318:	68 fc 81 42 00       	push   0x4281fc
  40331d:	e8 de 3a 00 00       	call   0x406e00
  403322:	83 c4 04             	add    esp,0x4
  403325:	6a ff                	push   0xffffffff
  403327:	e8 c4 39 00 00       	call   0x406cf0
  40332c:	83 c4 04             	add    esp,0x4
  40332f:	ff 75 24             	push   DWORD PTR [ebp+0x24]
  403332:	56                   	push   esi
  403333:	57                   	push   edi
  403334:	8d 45 fe             	lea    eax,[ebp-0x2]
  403337:	53                   	push   ebx
  403338:	50                   	push   eax
  403339:	e8 b0 fd ff ff       	call   0x4030ee
  40333e:	83 c4 14             	add    esp,0x14
  403341:	8b 45 28             	mov    eax,DWORD PTR [ebp+0x28]
  403344:	66 c7 00 02 00       	mov    WORD PTR [eax],0x2
  403349:	8b 4d 24             	mov    ecx,DWORD PTR [ebp+0x24]
  40334c:	66 29 5d 0c          	sub    WORD PTR [ebp+0xc],bx
  403350:	33 c0                	xor    eax,eax
  403352:	66 89 01             	mov    WORD PTR [ecx],ax
  403355:	51                   	push   ecx
  403356:	66 89 06             	mov    WORD PTR [esi],ax
  403359:	56                   	push   esi
  40335a:	ff 75 14             	push   DWORD PTR [ebp+0x14]
  40335d:	ff 75 0c             	push   DWORD PTR [ebp+0xc]
  403360:	8b 7d 08             	mov    edi,DWORD PTR [ebp+0x8]
  403363:	57                   	push   edi
  403364:	e8 85 fd ff ff       	call   0x4030ee
  403369:	66 8b 07             	mov    ax,WORD PTR [edi]
  40336c:	83 c4 14             	add    esp,0x14
  40336f:	8a cb                	mov    cl,bl
  403371:	66 d3 e0             	shl    ax,cl
  403374:	66 0b 45 fe          	or     ax,WORD PTR [ebp-0x2]
  403378:	66 89 07             	mov    WORD PTR [edi],ax
  40337b:	66 b8 01 00          	mov    ax,0x1
  40337f:	5f                   	pop    edi
  403380:	5e                   	pop    esi
  403381:	5b                   	pop    ebx
  403382:	8b e5                	mov    esp,ebp
  403384:	5d                   	pop    ebp
  403385:	c3                   	ret    
  403386:	55                   	push   ebp
  403387:	8b ec                	mov    ebp,esp
  403389:	53                   	push   ebx
  40338a:	66 33 db             	xor    bx,bx
  40338d:	56                   	push   esi
  40338e:	57                   	push   edi
  40338f:	8b 75 08             	mov    esi,DWORD PTR [ebp+0x8]
  403392:	8b 7d 0c             	mov    edi,DWORD PTR [ebp+0xc]
  403395:	ff 75 20             	push   DWORD PTR [ebp+0x20]
  403398:	0f bf c3             	movsx  eax,bx
  40339b:	66 43                	inc    bx
  40339d:	8d 0c 45 30 14 43 00 	lea    ecx,[eax*2+0x431430]
  4033a4:	ff 75 1c             	push   DWORD PTR [ebp+0x1c]
  4033a7:	ff 75 18             	push   DWORD PTR [ebp+0x18]
  4033aa:	ff 75 14             	push   DWORD PTR [ebp+0x14]
  4033ad:	ff 75 10             	push   DWORD PTR [ebp+0x10]
  4033b0:	57                   	push   edi
  4033b1:	56                   	push   esi
  4033b2:	6a 08                	push   0x8
  4033b4:	51                   	push   ecx
  4033b5:	e8 b6 fe ff ff       	call   0x403270
  4033ba:	83 c4 24             	add    esp,0x24
  4033bd:	66 83 fb 03          	cmp    bx,0x3
  4033c1:	7c d2                	jl     0x403395
  4033c3:	ff 75 20             	push   DWORD PTR [ebp+0x20]
  4033c6:	ff 75 1c             	push   DWORD PTR [ebp+0x1c]
  4033c9:	ff 75 18             	push   DWORD PTR [ebp+0x18]
  4033cc:	ff 75 14             	push   DWORD PTR [ebp+0x14]
  4033cf:	ff 75 10             	push   DWORD PTR [ebp+0x10]
  4033d2:	57                   	push   edi
  4033d3:	66 bb 01 00          	mov    bx,0x1
  4033d7:	56                   	push   esi
  4033d8:	6a 08                	push   0x8
  4033da:	68 36 14 43 00       	push   0x431436
  4033df:	e8 8c fe ff ff       	call   0x403270
  4033e4:	83 c4 24             	add    esp,0x24
  4033e7:	ff 75 20             	push   DWORD PTR [ebp+0x20]
  4033ea:	0f bf c3             	movsx  eax,bx
  4033ed:	66 43                	inc    bx
  4033ef:	8d 0c 45 36 14 43 00 	lea    ecx,[eax*2+0x431436]
  4033f6:	ff 75 1c             	push   DWORD PTR [ebp+0x1c]
  4033f9:	ff 75 18             	push   DWORD PTR [ebp+0x18]
  4033fc:	ff 75 14             	push   DWORD PTR [ebp+0x14]
  4033ff:	ff 75 10             	push   DWORD PTR [ebp+0x10]
  403402:	57                   	push   edi
  403403:	56                   	push   esi
  403404:	6a 05                	push   0x5
  403406:	51                   	push   ecx
  403407:	e8 64 fe ff ff       	call   0x403270
  40340c:	83 c4 24             	add    esp,0x24
  40340f:	66 83 fb 03          	cmp    bx,0x3
  403413:	7c d2                	jl     0x4033e7
  403415:	66 33 db             	xor    bx,bx
  403418:	ff 75 20             	push   DWORD PTR [ebp+0x20]
  40341b:	0f bf c3             	movsx  eax,bx
  40341e:	66 43                	inc    bx
  403420:	8d 0c 45 3c 14 43 00 	lea    ecx,[eax*2+0x43143c]
  403427:	ff 75 1c             	push   DWORD PTR [ebp+0x1c]
  40342a:	ff 75 18             	push   DWORD PTR [ebp+0x18]
  40342d:	ff 75 14             	push   DWORD PTR [ebp+0x14]
  403430:	ff 75 10             	push   DWORD PTR [ebp+0x10]
  403433:	57                   	push   edi
  403434:	56                   	push   esi
  403435:	6a 05                	push   0x5
  403437:	51                   	push   ecx
  403438:	e8 33 fe ff ff       	call   0x403270
  40343d:	83 c4 24             	add    esp,0x24
  403440:	66 83 fb 03          	cmp    bx,0x3
  403444:	7c d2                	jl     0x403418
  403446:	66 33 db             	xor    bx,bx
  403449:	ff 75 20             	push   DWORD PTR [ebp+0x20]
  40344c:	0f bf c3             	movsx  eax,bx
  40344f:	66 43                	inc    bx
  403451:	8d 0c 45 5a 14 43 00 	lea    ecx,[eax*2+0x43145a]
  403458:	ff 75 1c             	push   DWORD PTR [ebp+0x1c]
  40345b:	ff 75 18             	push   DWORD PTR [ebp+0x18]
  40345e:	ff 75 14             	push   DWORD PTR [ebp+0x14]
  403461:	ff 75 10             	push   DWORD PTR [ebp+0x10]
  403464:	57                   	push   edi
  403465:	56                   	push   esi
  403466:	6a 07                	push   0x7
  403468:	51                   	push   ecx
  403469:	e8 02 fe ff ff       	call   0x403270
  40346e:	83 c4 24             	add    esp,0x24
  403471:	66 83 fb 03          	cmp    bx,0x3
  403475:	7c d2                	jl     0x403449
  403477:	66 33 db             	xor    bx,bx
  40347a:	ff 75 20             	push   DWORD PTR [ebp+0x20]
  40347d:	0f bf c3             	movsx  eax,bx
  403480:	66 43                	inc    bx
  403482:	8d 0c 45 42 14 43 00 	lea    ecx,[eax*2+0x431442]
  403489:	ff 75 1c             	push   DWORD PTR [ebp+0x1c]
  40348c:	ff 75 18             	push   DWORD PTR [ebp+0x18]
  40348f:	ff 75 14             	push   DWORD PTR [ebp+0x14]
  403492:	ff 75 10             	push   DWORD PTR [ebp+0x10]
  403495:	57                   	push   edi
  403496:	56                   	push   esi
  403497:	6a 01                	push   0x1
  403499:	51                   	push   ecx
  40349a:	e8 d1 fd ff ff       	call   0x403270
  40349f:	83 c4 24             	add    esp,0x24
  4034a2:	66 83 fb 0c          	cmp    bx,0xc
  4034a6:	7c d2                	jl     0x40347a
  4034a8:	66 33 db             	xor    bx,bx
  4034ab:	ff 75 20             	push   DWORD PTR [ebp+0x20]
  4034ae:	0f bf c3             	movsx  eax,bx
  4034b1:	66 43                	inc    bx
  4034b3:	8d 0c 45 60 14 43 00 	lea    ecx,[eax*2+0x431460]
  4034ba:	ff 75 1c             	push   DWORD PTR [ebp+0x1c]
  4034bd:	ff 75 18             	push   DWORD PTR [ebp+0x18]
  4034c0:	ff 75 14             	push   DWORD PTR [ebp+0x14]
  4034c3:	ff 75 10             	push   DWORD PTR [ebp+0x10]
  4034c6:	57                   	push   edi
  4034c7:	56                   	push   esi
  4034c8:	6a 05                	push   0x5
  4034ca:	51                   	push   ecx
  4034cb:	e8 a0 fd ff ff       	call   0x403270
  4034d0:	83 c4 24             	add    esp,0x24
  4034d3:	66 83 fb 03          	cmp    bx,0x3
  4034d7:	7c d2                	jl     0x4034ab
  4034d9:	5f                   	pop    edi
  4034da:	5e                   	pop    esi
  4034db:	5b                   	pop    ebx
  4034dc:	5d                   	pop    ebp
  4034dd:	c3                   	ret    

; decode-output

/mnt/c/Users/ASUS/Documents/ChatGPT/np560/doc/sources/cybervoice-2000-20260907/member-16-00077c23.bin:     file format pei-i386


Disassembly of section .text:

00401ea9 <.text+0xea9>:
  401ea9:	55                   	push   ebp
  401eaa:	66 8b 44 24 20       	mov    ax,WORD PTR [esp+0x20]
  401eaf:	8b ec                	mov    ebp,esp
  401eb1:	83 ec 08             	sub    esp,0x8
  401eb4:	53                   	push   ebx
  401eb5:	56                   	push   esi
  401eb6:	66 33 f6             	xor    si,si
  401eb9:	57                   	push   edi
  401eba:	66 3b c6             	cmp    ax,si
  401ebd:	0f 8e a5 00 00 00    	jle    0x401f68
  401ec3:	66 89 45 f8          	mov    WORD PTR [ebp-0x8],ax
  401ec7:	8b 7d 18             	mov    edi,DWORD PTR [ebp+0x18]
  401eca:	ff 75 2c             	push   DWORD PTR [ebp+0x2c]
  401ecd:	ff 75 28             	push   DWORD PTR [ebp+0x28]
  401ed0:	ff 75 24             	push   DWORD PTR [ebp+0x24]
  401ed3:	ff 75 14             	push   DWORD PTR [ebp+0x14]
  401ed6:	ff 75 0c             	push   DWORD PTR [ebp+0xc]
  401ed9:	ff 75 10             	push   DWORD PTR [ebp+0x10]
  401edc:	ff 75 08             	push   DWORD PTR [ebp+0x8]
  401edf:	e8 a2 14 00 00       	call   0x403386
  401ee4:	83 c4 1c             	add    esp,0x1c
  401ee7:	e8 10 f9 ff ff       	call   0x4017fc
  401eec:	d9 05 ac 20 42 00    	fld    DWORD PTR ds:0x4220ac
  401ef2:	d9 05 b0 20 42 00    	fld    DWORD PTR ds:0x4220b0
  401ef8:	66 c7 45 fe 00 00    	mov    WORD PTR [ebp-0x2],0x0
  401efe:	0f bf 5d fe          	movsx  ebx,WORD PTR [ebp-0x2]
  401f02:	8d 0c 9d 00 00 00 00 	lea    ecx,[ebx*4+0x0]
  401f09:	03 0d 58 f9 42 00    	add    ecx,DWORD PTR ds:0x42f958
  401f0f:	d9 01                	fld    DWORD PTR [ecx]
  401f11:	d8 da                	fcomp  st(2)
  401f13:	df e0                	fnstsw ax
  401f15:	9e                   	sahf   
  401f16:	76 0d                	jbe    0x401f25
  401f18:	0f bf c6             	movsx  eax,si
  401f1b:	03 c3                	add    eax,ebx
  401f1d:	66 c7 04 47 ff 7f    	mov    WORD PTR [edi+eax*2],0x7fff
  401f23:	eb 24                	jmp    0x401f49
  401f25:	d8 11                	fcom   DWORD PTR [ecx]
  401f27:	df e0                	fnstsw ax
  401f29:	9e                   	sahf   
  401f2a:	76 0d                	jbe    0x401f39
  401f2c:	0f bf c6             	movsx  eax,si
  401f2f:	03 c3                	add    eax,ebx
  401f31:	66 c7 04 47 00 80    	mov    WORD PTR [edi+eax*2],0x8000
  401f37:	eb 10                	jmp    0x401f49
  401f39:	d9 01                	fld    DWORD PTR [ecx]
  401f3b:	e8 64 4f 00 00       	call   0x406ea4
  401f40:	0f bf ce             	movsx  ecx,si
  401f43:	03 cb                	add    ecx,ebx
  401f45:	66 89 04 4f          	mov    WORD PTR [edi+ecx*2],ax
  401f49:	66 ff 45 fe          	inc    WORD PTR [ebp-0x2]
  401f4d:	66 81 7d fe a8 00    	cmp    WORD PTR [ebp-0x2],0xa8
  401f53:	7c a9                	jl     0x401efe
  401f55:	dd d8                	fstp   st(0)
  401f57:	dd d8                	fstp   st(0)
  401f59:	66 81 c6 a8 00       	add    si,0xa8
  401f5e:	66 ff 4d f8          	dec    WORD PTR [ebp-0x8]
  401f62:	0f 85 62 ff ff ff    	jne    0x401eca
  401f68:	5f                   	pop    edi
  401f69:	5e                   	pop    esi
  401f6a:	5b                   	pop    ebx
  401f6b:	8b e5                	mov    esp,ebp
  401f6d:	5d                   	pop    ebp
  401f6e:	c3                   	ret    

; caller

/mnt/c/Users/ASUS/Documents/ChatGPT/np560/doc/sources/cybervoice-2000-20260907/member-16-00077c23.bin:     file format pei-i386


Disassembly of section .text:

00402bf4 <.text+0x1bf4>:
  402bf4:	55                   	push   ebp
  402bf5:	33 c0                	xor    eax,eax
  402bf7:	8b ec                	mov    ebp,esp
  402bf9:	83 ec 04             	sub    esp,0x4
  402bfc:	39 05 a4 d7 42 00    	cmp    DWORD PTR ds:0x42d7a4,eax
  402c02:	56                   	push   esi
  402c03:	74 40                	je     0x402c45
  402c05:	66 8b 0d 84 14 43 00 	mov    cx,WORD PTR ds:0x431484
  402c0c:	66 39 0d 5c de 42 00 	cmp    WORD PTR ds:0x42de5c,cx
  402c13:	7e 30                	jle    0x402c45
  402c15:	66 ff 05 84 14 43 00 	inc    WORD PTR ds:0x431484
  402c1c:	6a 02                	push   0x2
  402c1e:	be a8 14 43 00       	mov    esi,0x4314a8
  402c23:	a3 a4 d7 42 00       	mov    ds:0x42d7a4,eax
  402c28:	8d 45 fe             	lea    eax,[ebp-0x2]
  402c2b:	8b ce                	mov    ecx,esi
  402c2d:	50                   	push   eax
  402c2e:	e8 93 21 01 00       	call   0x414dc6
  402c33:	0f bf 4d fe          	movsx  ecx,WORD PTR [ebp-0x2]
  402c37:	51                   	push   ecx
  402c38:	a1 c0 14 43 00       	mov    eax,ds:0x4314c0
  402c3d:	50                   	push   eax
  402c3e:	8b ce                	mov    ecx,esi
  402c40:	e8 81 21 01 00       	call   0x414dc6
  402c45:	66 83 3d c0 15 43 00 	cmp    WORD PTR ds:0x4315c0,0x2
  402c4c:	02 
  402c4d:	75 5a                	jne    0x402ca9
  402c4f:	66 8b 15 84 14 43 00 	mov    dx,WORD PTR ds:0x431484
  402c56:	a1 bc 14 43 00       	mov    eax,ds:0x4314bc
  402c5b:	66 39 15 5c de 42 00 	cmp    WORD PTR ds:0x42de5c,dx
  402c62:	8b 0d c0 14 43 00    	mov    ecx,DWORD PTR ds:0x4314c0
  402c68:	66 c7 05 c0 15 43 00 	mov    WORD PTR ds:0x4315c0,0x1
  402c6f:	01 00 
  402c71:	89 0d bc 14 43 00    	mov    DWORD PTR ds:0x4314bc,ecx
  402c77:	a3 c0 14 43 00       	mov    ds:0x4314c0,eax
  402c7c:	7e 2b                	jle    0x402ca9
  402c7e:	66 ff 05 84 14 43 00 	inc    WORD PTR ds:0x431484
  402c85:	6a 02                	push   0x2
  402c87:	8d 45 fe             	lea    eax,[ebp-0x2]
  402c8a:	be a8 14 43 00       	mov    esi,0x4314a8
  402c8f:	50                   	push   eax
  402c90:	8b ce                	mov    ecx,esi
  402c92:	e8 2f 21 01 00       	call   0x414dc6
  402c97:	0f bf 4d fe          	movsx  ecx,WORD PTR [ebp-0x2]
  402c9b:	51                   	push   ecx
  402c9c:	a1 c0 14 43 00       	mov    eax,ds:0x4314c0
  402ca1:	50                   	push   eax
  402ca2:	8b ce                	mov    ecx,esi
  402ca4:	e8 1d 21 01 00       	call   0x414dc6
  402ca9:	a1 98 14 43 00       	mov    eax,ds:0x431498
  402cae:	39 05 80 14 43 00    	cmp    DWORD PTR ds:0x431480,eax
  402cb4:	7c 0d                	jl     0x402cc3
  402cb6:	0f bf 05 38 de 42 00 	movsx  eax,WORD PTR ds:0x42de38
  402cbd:	01 05 98 14 43 00    	add    DWORD PTR ds:0x431498,eax
  402cc3:	a1 98 14 43 00       	mov    eax,ds:0x431498
  402cc8:	39 05 80 14 43 00    	cmp    DWORD PTR ds:0x431480,eax
  402cce:	7f 27                	jg     0x402cf7
  402cd0:	c7 05 54 de 42 00 01 	mov    DWORD PTR ds:0x42de54,0x1
  402cd7:	00 00 00 
  402cda:	a1 80 14 43 00       	mov    eax,ds:0x431480
  402cdf:	66 2b 05 98 14 43 00 	sub    ax,WORD PTR ds:0x431498
  402ce6:	66 01 05 38 de 42 00 	add    WORD PTR ds:0x42de38,ax
  402ced:	a1 80 14 43 00       	mov    eax,ds:0x431480
  402cf2:	a3 98 14 43 00       	mov    ds:0x431498,eax
  402cf7:	66 a1 38 de 42 00    	mov    ax,ds:0x42de38
  402cfd:	68 c0 15 43 00       	push   0x4315c0
  402d02:	68 bc 15 43 00       	push   0x4315bc
  402d07:	8d 4d fc             	lea    ecx,[ebp-0x4]
  402d0a:	68 a0 14 43 00       	push   0x4314a0
  402d0f:	50                   	push   eax
  402d10:	66 a1 b8 14 43 00    	mov    ax,ds:0x4314b8
  402d16:	51                   	push   ecx
  402d17:	ff 75 08             	push   DWORD PTR [ebp+0x8]
  402d1a:	50                   	push   eax
  402d1b:	ff 35 c0 14 43 00    	push   DWORD PTR ds:0x4314c0
  402d21:	50                   	push   eax
  402d22:	ff 35 bc 14 43 00    	push   DWORD PTR ds:0x4314bc
  402d28:	e8 7c f1 ff ff       	call   0x401ea9
  402d2d:	0f bf 0d 38 de 42 00 	movsx  ecx,WORD PTR ds:0x42de38
  402d34:	83 c4 28             	add    esp,0x28
  402d37:	8b 45 0c             	mov    eax,DWORD PTR [ebp+0xc]
  402d3a:	69 c9 50 01 00 00    	imul   ecx,ecx,0x150
  402d40:	5e                   	pop    esi
  402d41:	89 08                	mov    DWORD PTR [eax],ecx
  402d43:	b8 01 00 00 00       	mov    eax,0x1
  402d48:	8b e5                	mov    esp,ebp
  402d4a:	5d                   	pop    ebp
  402d4b:	c3                   	ret    

